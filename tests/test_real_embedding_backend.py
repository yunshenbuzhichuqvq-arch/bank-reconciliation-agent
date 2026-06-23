from pathlib import Path

import pytest

from bank_reconciliation_agent.rag import retriever
from bank_reconciliation_agent.rag.retriever import (
    BGE_M3_EMBEDDING_DIMENSIONS,
    BGE_SMALL_EMBEDDING_DIMENSIONS,
    BuiltEmbeddingFunction,
    HashEmbeddingFunction,
    SentenceTransformerEmbeddingFunction,
    build_embedding_function,
)


def test_hash_backend_preserves_existing_embedding_vector() -> None:
    old_vector = retriever._embed_text("金额差异 对账不平")

    built_embedding = build_embedding_function("hash")

    assert built_embedding.effective_backend == "hash"
    assert isinstance(built_embedding.embedding_function, HashEmbeddingFunction)
    assert list(built_embedding.embedding_function(["金额差异 对账不平"])[0]) == old_vector


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

    built_embedding = build_embedding_function(backend)
    embedding_function = built_embedding.embedding_function

    assert built_embedding.effective_backend == backend
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

    built_embedding = build_embedding_function("bge_m3")

    assert built_embedding.effective_backend == "hash"
    assert isinstance(built_embedding.embedding_function, HashEmbeddingFunction)
    assert [warning["backend"] for warning in warnings] == ["bge_m3", "bge_small"]
    assert all(warning["event"] == "rag_embedding_backend_fallback" for warning in warnings)


def test_chroma_rule_store_uses_configured_backend(tmp_path: Path) -> None:
    store = retriever.ChromaRuleStore(
        chunks_path=tmp_path / "rule_chunks.jsonl",
        chroma_path=tmp_path / "chroma",
        embedding_backend="hash",
    )

    assert isinstance(store.embedding_function, HashEmbeddingFunction)
    assert store.embedding_backend == "hash"


def test_chroma_rule_store_uses_effective_backend_after_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        retriever,
        "build_embedding_function",
        lambda backend: BuiltEmbeddingFunction(HashEmbeddingFunction(), "hash"),
    )

    store = retriever.ChromaRuleStore(
        chunks_path=tmp_path / "rule_chunks.jsonl",
        chroma_path=tmp_path / "chroma",
        embedding_backend="bge_m3",
    )

    assert store.embedding_backend == "hash"
    assert store.collection_name == "rule_chunks_bank_enterprise_hash"
