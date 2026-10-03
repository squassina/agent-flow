from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, ForeignKey, DateTime
from database import Base


class Agent(Base):
    __tablename__ = "agents"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    llm_model = Column(String)
    system_prompt = Column(Text)
    tools = Column(String, default="")  # "calculator,web_search"
    use_memory = Column(Boolean, default=False)
    memory_max_chars = Column(Integer, default=1500)
    memory_model = Column(String, nullable=True)        # modelo (mais barato) usado só para atualizar a memória
    memory_every = Column(Integer, default=1)           # consolida a memória a cada N interações
    memory_min_chars = Column(Integer, default=200)     # ignora saídas menores que isso


class Flow(Base):
    __tablename__ = "flows"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    agent_ids = Column(String)  # "1,3,2"
    context_mode = Column(String, default="chain")  # chain | shared


class Run(Base):
    __tablename__ = "runs"
    id = Column(Integer, primary_key=True, index=True)
    flow_id = Column(Integer, ForeignKey("flows.id"))
    input = Column(Text)
    status = Column(String, default="running")  # running | done | error
    final_output = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class RunStep(Base):
    __tablename__ = "run_steps"
    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("runs.id"), index=True)
    step_no = Column(Integer)
    agent_id = Column(Integer, ForeignKey("agents.id"))
    input = Column(Text)
    output = Column(Text, nullable=True)
    error = Column(Text, nullable=True)


class TokenUsage(Base):
    __tablename__ = "token_usage"
    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=True)
    flow_id = Column(Integer, ForeignKey("flows.id"), nullable=True)
    agent_id = Column(Integer, ForeignKey("agents.id"))
    model = Column(String)
    tokens_used = Column(Integer)
    estimated_cost = Column(Float)
    kind = Column(String, default="run")  # run | memory
    timestamp = Column(DateTime, default=datetime.utcnow)


class AgentMemory(Base):
    """Memória persistente por agente: resumo compacto e limitado, reaproveitado entre execuções."""
    __tablename__ = "agent_memory"
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), unique=True, index=True)
    content = Column(Text, default="")
    updates = Column(Integer, default=0)
    pending = Column(Text, default="")                  # interações ainda não consolidadas
    pending_count = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow)
