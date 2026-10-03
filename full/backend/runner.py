import json
from litellm import completion, completion_cost

import models
from database import SessionLocal
from tools import AVAILABLE_TOOLS

MAX_TOOL_ITERATIONS = 5


def _run_tool(name: str, raw_args: str) -> str:
    try:
        if name not in AVAILABLE_TOOLS:
            return f"Erro: ferramenta '{name}' não existe."
        args = json.loads(raw_args or "{}")
        return str(AVAILABLE_TOOLS[name]["function"](**args))
    except Exception as e:
        return f"Erro ao executar '{name}': {e}"


def call_agent(agent: models.Agent, user_input: str, db, run_id: int, flow_id: int) -> str:
    messages = [
        {"role": "system", "content": agent.system_prompt or ""},
        {"role": "user", "content": user_input},
    ]
    names = [t.strip() for t in (agent.tools or "").split(",") if t.strip() in AVAILABLE_TOOLS]
    schemas = [AVAILABLE_TOOLS[t]["schema"] for t in names] or None

    tokens, cost, final = 0, 0.0, None

    def track(resp):
        nonlocal tokens, cost
        tokens += resp.usage.total_tokens
        try:
            cost += completion_cost(completion_response=resp) or 0.0
        except Exception:
            pass  # modelo sem preço mapeado

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
                messages.append({
                    "role": "tool", "tool_call_id": tc.id, "name": tc.function.name,
                    "content": _run_tool(tc.function.name, tc.function.arguments),
                })
        if final is None:  # loop terminou em tool call: força resposta final sem tools
            resp = completion(model=agent.llm_model, messages=messages)
            track(resp)
            final = resp.choices[0].message.content
    finally:
        if tokens:
            db.add(models.TokenUsage(run_id=run_id, flow_id=flow_id, agent_id=agent.id,
                                     model=agent.llm_model, tokens_used=tokens, estimated_cost=cost))
            db.commit()
    return final or ""


def execute_run(run_id: int):
    db = SessionLocal()  # sessão própria: a da requisição já foi fechada
    try:
        run = db.get(models.Run, run_id)
        flow = db.get(models.Flow, run.flow_id)
        current = run.input
        try:
            ids = [int(x) for x in flow.agent_ids.split(",") if x.strip()]
            for n, ag_id in enumerate(ids, 1):
                agent = db.get(models.Agent, ag_id)
                step = models.RunStep(run_id=run.id, step_no=n, agent_id=ag_id, input=current)
                db.add(step)
                db.commit()
                if not agent:
                    step.error = f"Agente {ag_id} não encontrado"
                    raise RuntimeError(step.error)
                try:
                    step.output = current = call_agent(agent, current, db, run.id, flow.id)
                    db.commit()
                except Exception as e:
                    step.error = str(e)
                    db.commit()
                    raise
            run.status, run.final_output = "done", current
        except Exception as e:
            run.status, run.final_output = "error", f"Falha: {e}"
        db.commit()
    finally:
        db.close()
