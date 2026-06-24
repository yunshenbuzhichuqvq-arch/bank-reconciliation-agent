import os
from pathlib import Path
from typing import Any

import pytest
from arq.connections import ArqRedis
from fakeredis.aioredis import FakeRedis


TEST_DB_PATH = Path("/private/tmp/bank_reconciliation_agent_tests.sqlite")
TEST_MEMORY_DB_PATH = Path("/private/tmp/bank_reconciliation_agent_memory_tests.sqlite")
TEST_CHECKPOINT_DB_PATH = Path("/private/tmp/bank_reconciliation_agent_checkpoint_tests.sqlite")
BGE_SMALL_MODEL_NAME = "BAAI/bge-small-zh-v1.5"

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


@pytest.fixture
def real_bge_small_model_class() -> type:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        pytest.skip(
            "sentence-transformers is not installed; install with `uv sync --extra embedding`"
        )

    try:
        model = SentenceTransformer(BGE_SMALL_MODEL_NAME, local_files_only=True)
    except Exception as exc:
        pytest.skip(f"{BGE_SMALL_MODEL_NAME} is not available in the local model cache: {exc}")

    class CachedSentenceTransformer:
        def __init__(self, model_name: str) -> None:
            if model_name != BGE_SMALL_MODEL_NAME:
                raise RuntimeError(f"unexpected opt-in model: {model_name}")
            self._model = model

        def encode(self, input_texts: list[str], normalize_embeddings: bool) -> Any:
            return self._model.encode(input_texts, normalize_embeddings=normalize_embeddings)

    return CachedSentenceTransformer
