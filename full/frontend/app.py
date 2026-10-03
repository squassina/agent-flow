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
memories = api("GET", "/memories/") or {}
agent_name = {a["id"]: a["name"] for a in agents}

tab_ag, tab_fl, tab_ex, tab_hi, tab_rp = st.tabs(["Agentes", "Fluxos", "Executar", "Histórico", "Relatório"])

# ---------- Agentes ----------
with tab_ag:
    c1, c2 = st.columns([1, 4])
    if c1.button("🔄 Atualizar modelos"):
        st.session_state["refresh_models"] = True
        st.rerun()
    c2.caption(f"{len(MODELS)} modelos · " + ("lista ao vivo" if mdata.get("live") else "lista padrão (sem chaves/erro)"))
    cheap = api("GET", "/models/cheapest?n=1") or []
    st.caption("💸 Memória automática usará: " + (f"**{cheap[0]['model']}** (${cheap[0]['input_per_1m']}/${cheap[0]['output_per_1m']} por 1M tokens entrada/saída)" if cheap else "o modelo do próprio agente (sem lista ao vivo de modelos)"))
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
        use_mem = st.checkbox("Memória persistente (resumo compacto reaproveitado entre execuções)")
        mem_max = st.number_input("Tamanho máx. da memória (caracteres)", 200, 8000, 1500, step=100)
        mem_model = st.text_input("Modelo da memória", placeholder="vazio = mais barato disponível (auto) · same = mesmo do agente · ou digite um modelo")
        mem_every = st.number_input("Consolidar a memória a cada N interações", 1, 100, 1)
        mem_min = st.number_input("Ignorar saídas menores que (caracteres)", 0, 5000, 200, step=50)
        if st.form_submit_button("Salvar") and name:
            if api("POST", "/agents/", json={"name": name, "model": model, "prompt": prompt, "tools": ",".join(tools),
                                              "use_memory": use_mem, "memory_max_chars": int(mem_max),
                                              "memory_model": mem_model, "memory_every": int(mem_every), "memory_min_chars": int(mem_min)}):
                st.rerun()
    st.subheader("Cadastrados")
    for a in agents:
        with st.expander(f"{a['id']} · {a['name']} ({a['llm_model']})"):
            n = st.text_input("Nome", a["name"], key=f"an{a['id']}")
            m = st.text_input("Modelo", a["llm_model"], key=f"am{a['id']}")
            t = st.multiselect("Ferramentas", tool_names,
                               default=[x for x in (a["tools"] or "").split(",") if x in tool_names], key=f"at{a['id']}")
            p = st.text_area("Prompt", a["system_prompt"], key=f"ap{a['id']}")
            um = st.checkbox("Memória persistente", bool(a.get("use_memory")), key=f"aum{a['id']}")
            mm = st.number_input("Tamanho máx. da memória (caracteres)", 200, 8000, int(a.get("memory_max_chars") or 1500), step=100, key=f"amm{a['id']}")
            mmod = st.text_input("Modelo da memória (vazio = auto mais barato · same = mesmo do agente)", a.get("memory_model") or "", key=f"amd{a['id']}")
            mev = st.number_input("Consolidar a cada N interações", 1, 100, int(a.get("memory_every") or 1), key=f"amv{a['id']}")
            mmn = st.number_input("Ignorar saídas menores que (caracteres)", 0, 5000, int(a.get("memory_min_chars") if a.get("memory_min_chars") is not None else 200), step=50, key=f"amn{a['id']}")
            mem = memories.get(str(a["id"]))
            if um or mem:
                mtxt = st.text_area(f"Memória atual ({mem['updates'] if mem else 0} atualizações, {mem['pending'] if mem else 0} interações pendentes; editável)", mem["content"] if mem else "", key=f"amt{a['id']}")
                mc1, mc2 = st.columns(2)
                if mc1.button("Salvar memória", key=f"ams{a['id']}") and api("PUT", f"/agents/{a['id']}/memory", json={"content": mtxt}):
                    st.rerun()
                if mc2.button("Limpar memória", key=f"amc{a['id']}") and api("DELETE", f"/agents/{a['id']}/memory") is not None:
                    st.rerun()
            c1, c2 = st.columns(2)
            if c1.button("Atualizar", key=f"au{a['id']}"):
                if api("PUT", f"/agents/{a['id']}", json={"name": n, "model": m, "prompt": p, "tools": ",".join(t),
                                                          "use_memory": um, "memory_max_chars": int(mm),
                                                          "memory_model": mmod, "memory_every": int(mev), "memory_min_chars": int(mmn)}):
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
            ctx = st.selectbox("Modo de contexto", ["chain", "shared"], format_func=lambda x: {
                "chain": "chain: cada agente recebe só a saída do anterior (mais barato)",
                "shared": "shared: pedido original + resumo dos passos antigos + saída anterior"}[x])
            if st.form_submit_button("Salvar") and fname and sel:
                if api("POST", "/flows/", json={"name": fname, "agent_ids": ",".join(map(str, sel)), "context_mode": ctx}):
                    st.rerun()
    st.subheader("Cadastrados")
    for f in flows:
        chain = " → ".join(agent_name.get(int(i), "?") for i in f["agent_ids"].split(",") if i.strip())
        c1, c2 = st.columns([6, 1])
        c1.write(f"**{f['id']} · {f['name']}** [{f.get('context_mode') or 'chain'}]: {chain}")
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
        if "kind" in df:
            st.subheader("Tokens por tipo (execução vs memória)")
            st.bar_chart(df.groupby("kind")["tokens_used"].sum())
        st.dataframe(df, use_container_width=True)
