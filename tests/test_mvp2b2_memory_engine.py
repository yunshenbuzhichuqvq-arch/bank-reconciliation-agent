from pathlib import Path

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.db.session import get_engine
from bank_reconciliation_agent.services.memory.engine import get_memory_engine


def test_memory_engine_uses_independent_sqlite_path() -> None:
    memory_engine = get_memory_engine()
    main_engine = get_engine()

    assert memory_engine.dialect.name == "sqlite"
    assert Path(settings.memory_sqlite_path).name == "bank_reconciliation_agent_memory_tests.sqlite"
    assert memory_engine.url.database == settings.memory_sqlite_path
    assert main_engine.url.database != memory_engine.url.database
