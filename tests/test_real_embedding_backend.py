from pathlib import Path

import pytest

from bank_reconciliation_agent.rag import retriever
from bank_reconciliation_agent.rag.retriever import (
    BGE_M3_EMBEDDING_DIMENSIONS,
    BGE_SMALL_EMBEDDING_DIMENSIONS,
    HashEmbeddingFunction,
    SentenceTransformerEmbeddingFunction,
    build_embedding_function,
)


def test_hash_backend_preserves_existing_embedding_vector() -> None:
    old_vector = retriever._embed_text("金额差异 对账不平")

    embedding_function = build_embedding_function("hash")

    assert isinstance(embedding_function, HashEmbeddingFunction)
    assert list(embedding_function(["金额差异 对账不平"])[0]) == old_vector


@pytest.mark.parametrize(
    ("backend", "model_name", "dimensions"),
    [
        ("bge_small", "BAAI/bge-small-zh-v1.5", BGE_SMALL_EMBEDDING_DIMENSIONS),
        ("bge_m3", "BAAI/bge-m3", BGE_M3_EMBEDDING_DIMENSIONS),
    ],
)
def test_real_backend_factory_returns_configured_sentence_transformer(
    backend: str,
    model_name: str,
    dimensions: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeModel:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        def encode(self, input_texts: list[str], normalize_embeddings: bool) -> list[list[float]]:
            return [[0.0] * dimensions for _ in input_texts]

    monkeypatch.setattr(
        SentenceTransformerEmbeddingFunction,
        "_load_sentence_transformer_class",
        staticmethod(lambda: FakeModel),
    )

    embedding_function = build_embedding_function(backend)

    assert isinstance(embedding_function, SentenceTransformerEmbeddingFunction)
    assert embedding_function.model_name == model_name
    assert embedding_function.get_config() == {
        "model_name": model_name,
        "dimensions": dimensions,
    }


def test_sentence_transformer_embedding_function_encodes_with_cached_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeVector:
        def __init__(self, values: list[float]) -> None:
            self._values = values

        def tolist(self) -> list[float]:
            return self._values

    class FakeModel:
        calls = 0

        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        def encode(self, input_texts: list[str], normalize_embeddings: bool) -> list[FakeVector]:
            FakeModel.calls += 1
            assert input_texts == ["规则一", "规则二"]
            assert normalize_embeddings is True
            return [FakeVector([1.0, 0.0]), FakeVector([0.0, 1.0])]

    monkeypatch.setattr(
        SentenceTransformerEmbeddingFunction,
        "_load_sentence_transformer_class",
        staticmethod(lambda: FakeModel),
    )

    embedding_function = SentenceTransformerEmbeddingFunction("fake-model", dimensions=2)

    assert [list(vector) for vector in embedding_function(["规则一", "规则二"])] == [
        [1.0, 0.0],
        [0.0, 1.0],
    ]
    assert [list(vector) for vector in embedding_function(["规则一", "规则二"])] == [
        [1.0, 0.0],
        [0.0, 1.0],
    ]
    assert FakeModel.calls == 2


def test_bge_m3_load_failure_falls_back_to_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_loading(self: SentenceTransformerEmbeddingFunction) -> list[list[float]]:
        raise RuntimeError(f"cannot load {self.model_name}")

    warnings: list[dict[str, str]] = []
    monkeypatch.setattr(SentenceTransformerEmbeddingFunction, "__call__", fail_loading)
    monkeypatch.setattr(
        retriever.log,
        "warning",
        lambda event, **kwargs: warnings.append({"event": event, **kwargs}),
    )

    embedding_function = build_embedding_function("bge_m3")

    assert isinstance(embedding_function, HashEmbeddingFunction)
    assert [warning["backend"] for warning in warnings] == ["bge_m3", "bge_small"]
    assert all(warning["event"] == "rag_embedding_backend_fallback" for warning in warnings)


def test_chroma_rule_store_uses_configured_backend(tmp_path: Path) -> None:
    store = retriever.ChromaRuleStore(
        chunks_path=tmp_path / "rule_chunks.jsonl",
        chroma_path=tmp_path / "chroma",
        embedding_backend="hash",
    )

    assert isinstance(store.embedding_function, HashEmbeddingFunction)
