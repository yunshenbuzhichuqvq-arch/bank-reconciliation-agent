import os
from pathlib import Path

import pytest
from arq.connections import ArqRedis
from fakeredis.aioredis import FakeRedis


TEST_DB_PATH = Path("/private/tmp/bank_reconciliation_agent_tests.sqlite")
TEST_MEMORY_DB_PATH = Path("/private/tmp/bank_reconciliation_agent_memory_tests.sqlite")
TEST_CHECKPOINT_DB_PATH = Path("/private/tmp/bank_reconciliation_agent_checkpoint_tests.sqlite")

if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()
if TEST_MEMORY_DB_PATH.exists():
    TEST_MEMORY_DB_PATH.unlink()
if TEST_CHECKPOINT_DB_PATH.exists():
    TEST_CHECKPOINT_DB_PATH.unlink()

os.environ["MYSQL_DSN"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["MEMORY_SQLITE_PATH"] = str(TEST_MEMORY_DB_PATH)
os.environ["CHECKPOINT_SQLITE_PATH"] = str(TEST_CHECKPOINT_DB_PATH)


@pytest.fixture
def fake_arq_redis(monkeypatch: pytest.MonkeyPatch) -> ArqRedis:
    from bank_reconciliation_agent.services import queue_client

    fake_redis = FakeRedis(decode_responses=False)
    redis_pool = ArqRedis(connection_pool=fake_redis.connection_pool)
    monkeypatch.setattr(queue_client, "_redis_pool", redis_pool)
    return redis_pool
