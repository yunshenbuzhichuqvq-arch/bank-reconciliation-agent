from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from bank_reconciliation_agent.core.config import settings


@lru_cache
def get_memory_engine() -> Engine:
    return create_engine(f"sqlite:///{settings.memory_sqlite_path}", future=True)
