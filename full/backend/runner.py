import json
from datetime import datetime
from litellm import completion, completion_cost

import models
from database import SessionLocal
from tools import AVAILABLE_TOOLS
from models_live import cheapest_model

MAX_TOOL_ITERATIONS = 5
SNIPPET_CHARS = 400      # tamanho dos resumos de passos antigos no modo "shared"
MEMORY_IO_CHARS = 1500   # quanto de cada interação é guardado/enviado ao atualizar a memória
PENDING_MAX_CHARS = 6000  # buffer máximo de interações pendentes (mantém as mais recentes)


def _clip(text: str, n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[:n].rstrip() + "…"


def _usage(resp):
    tokens = resp.usage.total_tokens
    try:
        cost = completion_cost(completion_response=resp) or 0.0
    except Exception:
        cost = 0.0  # modelo sem preço mapeado
    return tokens, cost


def _record(db, run_id, flow_id, agent, tokens, cost, kind="run", model=None):
    if tokens:
        db.add(models.TokenUsage(run_id=run_id, flow_id=flow_id, agent_id=agent.id, model=model or agent.llm_model,
                                 tokens_used=tokens, estimated_cost=cost, kind=kind))
        db.commit()


def _run_tool(name: str, raw_args: str) -> str:
    try:
        if name not in AVAILABLE_TOOLS:
            return f"Erro: ferramenta '{name}' não existe."
        args = json.loads(raw_args or "{}")
        return str(AVAILABLE_TOOLS[name]["function"](**args))
    except Exception as e:
        return f"Erro ao executar '{name}': {e}"


# ---------- memória ----------
def _get_memory(db, agent_id):
    return db.query(models.AgentMemory).filter_by(agent_id=agent_id).first()


def update_memory(agent, user_input, output, db, run_id, flow_id):
    """Acumula a interação e só consolida a memória a cada N interações, com um modelo (mais barato) opcional.
    Saídas curtas são ignoradas. Nunca derruba a execução."""
    try:
        if len((output or "").strip()) < (agent.memory_min_chars or 0):
            return
        mem = _get_memory(db, agent.id)
        if not mem:
            mem = models.AgentMemory(agent_id=agent.id, content="", updates=0, pending="", pending_count=0)
            db.add(mem)
        entry = f"Input: {_clip(user_input, MEMORY_IO_CHARS)}\nOutput: {_clip(output, MEMORY_IO_CHARS)}"
        pending = (f"{mem.pending}\n---\n" if mem.pending else "") + entry
        mem.pending = pending[-PENDING_MAX_CHARS:]
        mem.pending_count = (mem.pending_count or 0) + 1
        db.commit()
        if mem.pending_count < max(agent.memory_every or 1, 1):
            return  # ainda acumulando: nenhuma chamada ao LLM

        limit = agent.memory_max_chars or 1500
        choice = (agent.memory_model or "").strip()
        if choice == "same":
            model = agent.llm_model
        elif choice:
            model = choice
        else:  # automático: modelo mais barato disponível (LiteLLM), senão o do próprio agente
            model = cheapest_model() or agent.llm_model
        system = ("You maintain the long-term memory of an AI agent. Merge the existing memory with the new "
                  "interactions. Keep only durable, reusable information: facts, user preferences, decisions, "
                  "conventions, open tasks. Drop transient details and duplicates. Reply with the updated memory "
                  f"only, as concise notes, at most {limit} characters.")
        user = (f"EXISTING MEMORY:\n{mem.content or '(empty)'}\n\nNEW INTERACTIONS:\n{mem.pending}")
        resp = completion(model=model, messages=[{"role": "system", "content": system},
                                                 {"role": "user", "content": user}])
        tokens, cost = _usage(resp)
        _record(db, run_id, flow_id, agent, tokens, cost, kind="memory", model=model)
        text = (resp.choices[0].message.content or "").strip()[:limit]
        if text:
            mem.content, mem.updates, mem.updated_at = text, (mem.updates or 0) + 1, datetime.utcnow()
            mem.pending, mem.pending_count = "", 0
            db.commit()
    except Exception:
        db.rollback()  # o buffer pendente já está salvo: tenta de novo na próxima vez


# ---------- execução ----------
def call_agent(agent, user_input, db, run_id, flow_id) -> str:
    system = agent.system_prompt or ""
    if agent.use_memory:
        mem = _get_memory(db, agent.id)
        if mem and mem.content:
            system += f"\n\n## Your memory from previous runs\n{mem.content}"
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user_input}]
    names = [t.strip() for t in (agent.tools or "").split(",") if t.strip() in AVAILABLE_TOOLS]
    schemas = [AVAILABLE_TOOLS[t]["schema"] for t in names] or None

    tokens, cost, final = 0, 0.0, None

    def track(resp):
        nonlocal tokens, cost
        t, c = _usage(resp)
        tokens, cost = tokens + t, cost + c

    try:
        for _ in range(MAX_TOOL_ITERATIONS):
            resp = completion(model=agent.llm_model, messages=messages, tools=schemas)
            track(resp)
            msg = resp.choices[0].message
            messages.append(msg)
            if not msg.tool_calls:
                final = msg.content
                break
            for tc in msg.tool_calls:
                messages.append({"role": "tool", "tool_call_id": tc.id, "name": tc.function.name,
                                 "content": _run_tool(tc.function.name, tc.function.arguments)})
        if final is None:  # loop terminou em tool call: força resposta final sem tools
            resp = completion(model=agent.llm_model, messages=messages)
            track(resp)
            final = resp.choices[0].message.content
    finally:
        _record(db, run_id, flow_id, agent, tokens, cost)
    return final or ""


def build_input(mode, original, history, current):
    """chain: só a saída anterior. shared: pedido original + passos antigos condensados + saída anterior completa."""
    if mode != "shared" or not history:
        return current
    parts = [f"## Original request\n{original}"]
    older = [f"- Step {n} ({name}): {_clip(out, SNIPPET_CHARS)}" for n, name, out in history[:-1]]
    if older:
        parts.append("## Earlier steps (condensed)\n" + "\n".join(older))
    parts.append(f"## Previous step output\n{current}")
    return "\n\n".join(parts)


def execute_run(run_id: int):
    db = SessionLocal()  # sessão própria: a da requisição já foi fechada
    try:
        run = db.get(models.Run, run_id)
        flow = db.get(models.Flow, run.flow_id)
        mode = flow.context_mode or "chain"
        current, history = run.input, []
        try:
            ids = [int(x) for x in flow.agent_ids.split(",") if x.strip()]
            for n, ag_id in enumerate(ids, 1):
                agent = db.get(models.Agent, ag_id)
                step_input = build_input(mode, run.input, history, current)
                step = models.RunStep(run_id=run.id, step_no=n, agent_id=ag_id, input=step_input)
                db.add(step)
                db.commit()
                if not agent:
                    step.error = f"Agente {ag_id} não encontrado"
                    raise RuntimeError(step.error)
                try:
                    step.output = current = call_agent(agent, step_input, db, run.id, flow.id)
                    db.commit()
                except Exception as e:
                    step.error = str(e)
                    db.commit()
                    raise
                history.append((n, agent.name, current))
                if agent.use_memory:
                    update_memory(agent, step_input, current, db, run.id, flow.id)
            run.status, run.final_output = "done", current
        except Exception as e:
            run.status, run.final_output = "error", f"Falha: {e}"
        db.commit()
    finally:
        db.close()
