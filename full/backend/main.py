from datetime import datetime
from typing import Literal
from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()

from database import engine, Base, get_db, migrate  # noqa: E402
import models  # noqa: E402
from runner import execute_run  # noqa: E402
from tools import AVAILABLE_TOOLS  # noqa: E402
from models_live import list_models, cheapest_models  # noqa: E402

Base.metadata.create_all(bind=engine)
migrate()
app = FastAPI(title="Agent Flow API")


class AgentIn(BaseModel):
    name: str
    model: str
    prompt: str
    tools: str = ""
    use_memory: bool = False
    memory_max_chars: int = 1500
    memory_model: str = ""
    memory_every: int = Field(1, ge=1, le=100)
    memory_min_chars: int = Field(200, ge=0)


class FlowIn(BaseModel):
    name: str
    agent_ids: str
    context_mode: Literal["chain", "shared"] = "chain"


class MemoryIn(BaseModel):
    content: str


class RunIn(BaseModel):
    flow_id: int
    user_input: str


def _get_or_404(db, model, id_):
    obj = db.get(model, id_)
    if not obj:
        raise HTTPException(404, f"{model.__name__} {id_} não encontrado")
    return obj


@app.get("/tools/")
def list_tools():
    return list(AVAILABLE_TOOLS)


@app.get("/models/")
def get_models(refresh: bool = False):
    return list_models(refresh)


@app.get("/models/cheapest")
def get_cheapest(n: int = 5, refresh: bool = False):
    return cheapest_models(n, refresh)


# ---- Agentes ----
@app.post("/agents/")
def create_agent(body: AgentIn, db: Session = Depends(get_db)):
    obj = models.Agent(name=body.name, llm_model=body.model, system_prompt=body.prompt, tools=body.tools,
                       use_memory=body.use_memory, memory_max_chars=body.memory_max_chars,
                       memory_model=body.memory_model.strip() or None,
                       memory_every=body.memory_every, memory_min_chars=body.memory_min_chars)
    db.add(obj); db.commit(); db.refresh(obj)
    return obj


@app.get("/agents/")
def get_agents(db: Session = Depends(get_db)):
    return db.query(models.Agent).all()


@app.put("/agents/{agent_id}")
def update_agent(agent_id: int, body: AgentIn, db: Session = Depends(get_db)):
    obj = _get_or_404(db, models.Agent, agent_id)
    obj.name, obj.llm_model, obj.system_prompt, obj.tools = body.name, body.model, body.prompt, body.tools
    obj.use_memory, obj.memory_max_chars = body.use_memory, body.memory_max_chars
    obj.memory_model, obj.memory_every = body.memory_model.strip() or None, body.memory_every
    obj.memory_min_chars = body.memory_min_chars
    db.commit(); db.refresh(obj)
    return obj


@app.delete("/agents/{agent_id}")
def delete_agent(agent_id: int, db: Session = Depends(get_db)):
    obj = _get_or_404(db, models.Agent, agent_id)
    in_use = [f.name for f in db.query(models.Flow).all()
              if str(agent_id) in [x.strip() for x in f.agent_ids.split(",")]]
    if in_use:
        raise HTTPException(409, f"Agente usado nos fluxos: {', '.join(in_use)}")
    db.query(models.AgentMemory).filter_by(agent_id=agent_id).delete()
    db.delete(obj); db.commit()
    return {"deleted": agent_id}


# ---- Memória dos agentes ----
@app.get("/memories/")
def list_memories(db: Session = Depends(get_db)):
    return {str(m.agent_id): {"content": m.content, "updates": m.updates, "pending": m.pending_count or 0, "updated_at": m.updated_at}
            for m in db.query(models.AgentMemory).all()}


@app.put("/agents/{agent_id}/memory")
def set_memory(agent_id: int, body: MemoryIn, db: Session = Depends(get_db)):
    _get_or_404(db, models.Agent, agent_id)
    m = db.query(models.AgentMemory).filter_by(agent_id=agent_id).first()
    if not m:
        m = models.AgentMemory(agent_id=agent_id, updates=0)
        db.add(m)
    m.content, m.updated_at = body.content, datetime.utcnow()
    db.commit()
    return {"agent_id": agent_id, "chars": len(m.content)}


@app.delete("/agents/{agent_id}/memory")
def clear_memory(agent_id: int, db: Session = Depends(get_db)):
    db.query(models.AgentMemory).filter_by(agent_id=agent_id).delete()
    db.commit()
    return {"cleared": agent_id}


# ---- Fluxos ----
@app.post("/flows/")
def create_flow(body: FlowIn, db: Session = Depends(get_db)):
    ids = [int(x) for x in body.agent_ids.split(",") if x.strip()]
    if not ids:
        raise HTTPException(422, "Selecione ao menos um agente")
    for i in ids:
        _get_or_404(db, models.Agent, i)
    obj = models.Flow(name=body.name, agent_ids=",".join(map(str, ids)), context_mode=body.context_mode)
    db.add(obj); db.commit(); db.refresh(obj)
    return obj


@app.get("/flows/")
def get_flows(db: Session = Depends(get_db)):
    return db.query(models.Flow).all()


@app.put("/flows/{flow_id}")
def update_flow(flow_id: int, body: FlowIn, db: Session = Depends(get_db)):
    obj = _get_or_404(db, models.Flow, flow_id)
    obj.name, obj.agent_ids, obj.context_mode = body.name, body.agent_ids, body.context_mode
    db.commit(); db.refresh(obj)
    return obj


@app.delete("/flows/{flow_id}")
def delete_flow(flow_id: int, db: Session = Depends(get_db)):
    obj = _get_or_404(db, models.Flow, flow_id)
    db.delete(obj); db.commit()
    return {"deleted": flow_id}


# ---- Execução ----
@app.post("/execute/flow/")
def execute_flow(body: RunIn, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    _get_or_404(db, models.Flow, body.flow_id)
    run = models.Run(flow_id=body.flow_id, input=body.user_input, status="running")
    db.add(run); db.commit(); db.refresh(run)
    background_tasks.add_task(execute_run, run.id)
    return {"run_id": run.id, "status": run.status}


@app.get("/runs/")
def list_runs(limit: int = 50, db: Session = Depends(get_db)):
    return db.query(models.Run).order_by(models.Run.id.desc()).limit(limit).all()


@app.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = _get_or_404(db, models.Run, run_id)
    steps = db.query(models.RunStep).filter_by(run_id=run_id).order_by(models.RunStep.step_no).all()
    agents = {a.id: a.name for a in db.query(models.Agent).all()}
    return {
        "id": run.id, "flow_id": run.flow_id, "input": run.input, "status": run.status,
        "final_output": run.final_output, "created_at": run.created_at,
        "steps": [{"step_no": s.step_no, "agent_id": s.agent_id, "agent": agents.get(s.agent_id, "?"),
                   "input": s.input, "output": s.output, "error": s.error} for s in steps],
    }


# ---- Relatório ----
@app.get("/reports/tokens/")
def get_token_reports(db: Session = Depends(get_db)):
    agents = {a.id: a.name for a in db.query(models.Agent).all()}
    flows = {f.id: f.name for f in db.query(models.Flow).all()}
    return [{"id": u.id, "run_id": u.run_id, "flow": flows.get(u.flow_id, "-"),
             "agent": agents.get(u.agent_id, "?"), "model": u.model,
             "kind": u.kind or "run", "tokens_used": u.tokens_used, "estimated_cost": u.estimated_cost,
             "timestamp": u.timestamp} for u in db.query(models.TokenUsage).all()]
