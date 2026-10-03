import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///./agent_flow.db"), connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate():
    """Adiciona colunas novas em bancos criados por versões anteriores (SQLite)."""
    cols = [
        ("agents", "use_memory", "BOOLEAN DEFAULT 0"),
        ("agents", "memory_max_chars", "INTEGER DEFAULT 1500"),
        ("agents", "memory_model", "VARCHAR"),
        ("agents", "memory_every", "INTEGER DEFAULT 1"),
        ("agents", "memory_min_chars", "INTEGER DEFAULT 200"),
        ("agent_memory", "pending", "TEXT DEFAULT ''"),
        ("agent_memory", "pending_count", "INTEGER DEFAULT 0"),
        ("flows", "context_mode", "VARCHAR DEFAULT 'chain'"),
        ("token_usage", "kind", "VARCHAR DEFAULT 'run'"),
    ]
    with engine.begin() as c:
        for table, col, ddl in cols:
            exists = [r[1] for r in c.execute(text(f"PRAGMA table_info({table})"))]
            if exists and col not in exists:
                c.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
