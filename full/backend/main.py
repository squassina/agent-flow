from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()

from database import engine, Base, get_db  # noqa: E402
import models  # noqa: E402
from runner import execute_run  # noqa: E402
from tools import AVAILABLE_TOOLS  # noqa: E402
from models_live import list_models  # noqa: E402

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Agent Flow API")


class AgentIn(BaseModel):
    name: str
    model: str
    prompt: str
    tools: str = ""


class FlowIn(BaseModel):
    name: str
    agent_ids: str


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


# ---- Agentes ----
@app.post("/agents/")
def create_agent(body: AgentIn, db: Session = Depends(get_db)):
    obj = models.Agent(name=body.name, llm_model=body.model, system_prompt=body.prompt, tools=body.tools)
    db.add(obj); db.commit(); db.refresh(obj)
    return obj


@app.get("/agents/")
def get_agents(db: Session = Depends(get_db)):
    return db.query(models.Agent).all()


@app.put("/agents/{agent_id}")
def update_agent(agent_id: int, body: AgentIn, db: Session = Depends(get_db)):
    obj = _get_or_404(db, models.Agent, agent_id)
    obj.name, obj.llm_model, obj.system_prompt, obj.tools = body.name, body.model, body.prompt, body.tools
    db.commit(); db.refresh(obj)
    return obj


@app.delete("/agents/{agent_id}")
def delete_agent(agent_id: int, db: Session = Depends(get_db)):
    obj = _get_or_404(db, models.Agent, agent_id)
    in_use = [f.name for f in db.query(models.Flow).all()
              if str(agent_id) in [x.strip() for x in f.agent_ids.split(",")]]
    if in_use:
        raise HTTPException(409, f"Agente usado nos fluxos: {', '.join(in_use)}")
    db.delete(obj); db.commit()
    return {"deleted": agent_id}


# ---- Fluxos ----
@app.post("/flows/")
def create_flow(body: FlowIn, db: Session = Depends(get_db)):
    ids = [int(x) for x in body.agent_ids.split(",") if x.strip()]
    if not ids:
        raise HTTPException(422, "Selecione ao menos um agente")
    for i in ids:
        _get_or_404(db, models.Agent, i)
    obj = models.Flow(name=body.name, agent_ids=",".join(map(str, ids)))
    db.add(obj); db.commit(); db.refresh(obj)
    return obj


@app.get("/flows/")
def get_flows(db: Session = Depends(get_db)):
    return db.query(models.Flow).all()


@app.put("/flows/{flow_id}")
def update_flow(flow_id: int, body: FlowIn, db: Session = Depends(get_db)):
    obj = _get_or_404(db, models.Flow, flow_id)
    obj.name, obj.agent_ids = body.name, body.agent_ids
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
             "tokens_used": u.tokens_used, "estimated_cost": u.estimated_cost,
             "timestamp": u.timestamp} for u in db.query(models.TokenUsage).all()]
