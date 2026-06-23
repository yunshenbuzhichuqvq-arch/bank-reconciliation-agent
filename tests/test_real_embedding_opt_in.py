from pathlib import Path

import pytest

from bank_reconciliation_agent.rag import retriever
from bank_reconciliation_agent.rag.retriever import (
    BGE_SMALL_EMBEDDING_DIMENSIONS,
    ChromaRuleStore,
    HashEmbeddingFunction,
    SentenceTransformerEmbeddingFunction,
)
from scripts.build_rule_chunks import build_rule_chunks


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.embedding_real
def test_bge_small_loads_from_local_cache_with_expected_dimensions(
    real_bge_small_model_class,
) -> None:
    embedding_function = SentenceTransformerEmbeddingFunction(
        "BAAI/bge-small-zh-v1.5",
        dimensions=BGE_SMALL_EMBEDDING_DIMENSIONS,
    )
    embedding_function._load_sentence_transformer_class = staticmethod(
        lambda: real_bge_small_model_class
    )

    embedding = embedding_function(["银企对账发现银行有流水但企业没有入账"])[0]

    assert len(embedding) == BGE_SMALL_EMBEDDING_DIMENSIONS


@pytest.mark.embedding_real
def test_bge_small_rebuilds_backend_specific_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_bge_small_model_class,
) -> None:
    chunks_path = tmp_path / "rule_chunks_bank_enterprise.jsonl"
    build_rule_chunks(
        sources_path=ROOT / "data/rag/sources_bank_enterprise.json",
        output_path=chunks_path,
    )
    monkeypatch.setattr(
        SentenceTransformerEmbeddingFunction,
        "_load_sentence_transformer_class",
        staticmethod(lambda: real_bge_small_model_class),
    )

    store = ChromaRuleStore(
        chunks_path=chunks_path,
        chroma_path=tmp_path / "chroma",
        embedding_backend="bge_small",
    )

    rebuilt_counts = store.rebuild_indexes(scenarios=("BANK_ENTERPRISE",))

    assert rebuilt_counts["BANK_ENTERPRISE"] > 0
    assert store.collection("BANK_ENTERPRISE").count() == rebuilt_counts["BANK_ENTERPRISE"]
    assert store.collection_name == "rule_chunks_bank_enterprise_bge_small"


@pytest.mark.embedding_real
def test_real_backend_load_failure_logs_fallback_warning(
    monkeypatch: pytest.MonkeyPatch,
    real_bge_small_model_class,
) -> None:
    def fail_loading(self: SentenceTransformerEmbeddingFunction) -> list[list[float]]:
        raise RuntimeError(f"cannot load {self.model_name}")

    warnings: list[dict[str, str]] = []
    monkeypatch.setattr(SentenceTransformerEmbeddingFunction, "__call__", fail_loading)
    monkeypatch.setattr(
        retriever.log,
        "warning",
        lambda event, **kwargs: warnings.append({"event": event, **kwargs}),
    )

    built_embedding = retriever.build_embedding_function("bge_m3")

    assert built_embedding.effective_backend == "hash"
    assert isinstance(built_embedding.embedding_function, HashEmbeddingFunction)
    assert [warning["backend"] for warning in warnings] == ["bge_m3", "bge_small"]
    assert all(warning["event"] == "rag_embedding_backend_fallback" for warning in warnings)
