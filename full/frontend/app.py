import os
import requests
import pandas as pd
import streamlit as st

API = os.getenv("API_URL", "http://localhost:8000")
ICON = {"running": "⏳", "done": "✅", "error": "❌"}

st.set_page_config(page_title="Agent Flow", layout="wide")
st.title("🤖 Agent Flow")


def api(method, path, **kw):
    try:
        r = requests.request(method, f"{API}{path}", timeout=30, **kw)
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text)
            except Exception:
                detail = r.text
            st.error(f"Erro {r.status_code}: {detail}")
            return None
        return r.json()
    except requests.RequestException as e:
        st.error(f"Backend indisponível: {e}")
        return None


agents = api("GET", "/agents/") or []
flows = api("GET", "/flows/") or []
tool_names = api("GET", "/tools/") or []
if st.session_state.pop("refresh_models", False):
    mdata = api("GET", "/models/?refresh=true") or {}
else:
    mdata = api("GET", "/models/") or {}
MODELS = mdata.get("models", [])
agent_name = {a["id"]: a["name"] for a in agents}

tab_ag, tab_fl, tab_ex, tab_hi, tab_rp = st.tabs(["Agentes", "Fluxos", "Executar", "Histórico", "Relatório"])

# ---------- Agentes ----------
with tab_ag:
    c1, c2 = st.columns([1, 4])
    if c1.button("🔄 Atualizar modelos"):
        st.session_state["refresh_models"] = True
        st.rerun()
    c2.caption(f"{len(MODELS)} modelos · " + ("lista ao vivo" if mdata.get("live") else "lista padrão (sem chaves/erro)"))
    for prov, err in (mdata.get("errors") or {}).items():
        st.caption(f"⚠️ {prov}: {err}")
    with st.form("agent_form", clear_on_submit=True):
        st.subheader("Novo agente")
        name = st.text_input("Nome")
        model_sel = st.selectbox("Modelo LLM (lista ao vivo)", MODELS)
        model_custom = st.text_input("Ou digite o modelo manualmente (tem prioridade)",
                                     placeholder="ex: gemini/gemini-2.5-flash, gpt-4o, claude-sonnet-4-5")
        model = model_custom.strip() or model_sel
        tools = st.multiselect("Ferramentas", tool_names)
        prompt = st.text_area("System prompt")
        if st.form_submit_button("Salvar") and name:
            if api("POST", "/agents/", json={"name": name, "model": model, "prompt": prompt, "tools": ",".join(tools)}):
                st.rerun()
    st.subheader("Cadastrados")
    for a in agents:
        with st.expander(f"{a['id']} · {a['name']} ({a['llm_model']})"):
            n = st.text_input("Nome", a["name"], key=f"an{a['id']}")
            m = st.text_input("Modelo", a["llm_model"], key=f"am{a['id']}")
            t = st.multiselect("Ferramentas", tool_names,
                               default=[x for x in (a["tools"] or "").split(",") if x in tool_names], key=f"at{a['id']}")
            p = st.text_area("Prompt", a["system_prompt"], key=f"ap{a['id']}")
            c1, c2 = st.columns(2)
            if c1.button("Atualizar", key=f"au{a['id']}"):
                if api("PUT", f"/agents/{a['id']}", json={"name": n, "model": m, "prompt": p, "tools": ",".join(t)}):
                    st.rerun()
            if c2.button("Excluir", key=f"ad{a['id']}"):
                if api("DELETE", f"/agents/{a['id']}") is not None:
                    st.rerun()

# ---------- Fluxos ----------
with tab_fl:
    if not agents:
        st.warning("Cadastre agentes primeiro.")
    else:
        with st.form("flow_form", clear_on_submit=True):
            st.subheader("Novo fluxo")
            fname = st.text_input("Nome (ex: Analista → Tradutor)")
            sel = st.multiselect("Agentes na ordem de execução", list(agent_name), format_func=lambda i: f"{i} - {agent_name[i]}")
            if st.form_submit_button("Salvar") and fname and sel:
                if api("POST", "/flows/", json={"name": fname, "agent_ids": ",".join(map(str, sel))}):
                    st.rerun()
    st.subheader("Cadastrados")
    for f in flows:
        chain = " → ".join(agent_name.get(int(i), "?") for i in f["agent_ids"].split(",") if i.strip())
        c1, c2 = st.columns([6, 1])
        c1.write(f"**{f['id']} · {f['name']}**: {chain}")
        if c2.button("Excluir", key=f"fd{f['id']}"):
            api("DELETE", f"/flows/{f['id']}")
            st.rerun()


# ---------- visualização de run ----------
@st.fragment(run_every=2)
def show_run(run_id: int):
    run = api("GET", f"/runs/{run_id}")
    if not run:
        return
    st.markdown(f"### Run #{run['id']} {ICON.get(run['status'], '')} {run['status']}")
    for s in run["steps"]:
        with st.expander(f"Passo {s['step_no']} · {s['agent']}", expanded=run["status"] == "running"):
            st.caption("Entrada"); st.text(s["input"])
            if s["error"]:
                st.error(s["error"])
            elif s["output"] is not None:
                st.caption("Saída"); st.markdown(s["output"])
            else:
                st.info("Executando...")
    if run["status"] != "running":
        (st.error if run["status"] == "error" else st.success)(run["final_output"] or "")


# ---------- Executar ----------
with tab_ex:
    if not flows:
        st.warning("Nenhum fluxo cadastrado.")
    else:
        fid = st.selectbox("Fluxo", [f["id"] for f in flows],
                           format_func=lambda i: next(f"{f['id']} - {f['name']}" for f in flows if f["id"] == i))
        text = st.text_area("Entrada inicial")
        if st.button("Iniciar execução") and text:
            res = api("POST", "/execute/flow/", json={"flow_id": fid, "user_input": text})
            if res:
                st.session_state["run_id"] = res["run_id"]
        if "run_id" in st.session_state:
            show_run(st.session_state["run_id"])

# ---------- Histórico ----------
with tab_hi:
    runs = api("GET", "/runs/") or []
    if not runs:
        st.info("Nenhuma execução ainda.")
    else:
        fl_name = {f["id"]: f["name"] for f in flows}
        for r in runs:
            if st.button(f"{ICON.get(r['status'], '')} #{r['id']} · {fl_name.get(r['flow_id'], '?')} · {r['created_at'][:19]}", key=f"h{r['id']}"):
                st.session_state["hist_run"] = r["id"]
        if "hist_run" in st.session_state:
            st.divider()
            show_run(st.session_state["hist_run"])

# ---------- Relatório ----------
with tab_rp:
    st.button("Atualizar")
    rows = api("GET", "/reports/tokens/") or []
    if not rows:
        st.warning("Nenhum dado registrado.")
    else:
        df = pd.DataFrame(rows)
        c1, c2 = st.columns(2)
        c1.metric("Custo total (USD)", f"${df['estimated_cost'].sum():.4f}")
        c2.metric("Tokens totais", f"{df['tokens_used'].sum():,}")
        for col, label in [("agent", "agente"), ("model", "modelo"), ("flow", "fluxo")]:
            st.subheader(f"Custo por {label}")
            st.bar_chart(df.groupby(col)["estimated_cost"].sum())
        st.dataframe(df, use_container_width=True)
