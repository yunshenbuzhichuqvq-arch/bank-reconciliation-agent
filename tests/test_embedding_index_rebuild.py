from pathlib import Path

import chromadb

from bank_reconciliation_agent.rag import retriever
from bank_reconciliation_agent.rag.retriever import ChromaRuleStore
from scripts import eval_rag
from scripts.build_rule_chunks import build_rule_chunks


ROOT = Path(__file__).resolve().parents[1]


def _build_scenario_chunks(tmp_path: Path) -> Path:
    bank_chunks_path = tmp_path / "rule_chunks_bank_enterprise.jsonl"
    build_rule_chunks(
        sources_path=ROOT / "data/rag/sources_bank_enterprise.json",
        output_path=bank_chunks_path,
    )
    build_rule_chunks(
        sources_path=ROOT / "data/rag/sources_bank_clearing.json",
        output_path=tmp_path / "rule_chunks_bank_clearing.jsonl",
    )
    return bank_chunks_path


def test_collection_name_includes_backend_dimension() -> None:
    assert (
        ChromaRuleStore._collection_name_for_scenario("BANK_ENTERPRISE", "hash")
        == "rule_chunks_bank_enterprise_hash"
    )
    assert (
        ChromaRuleStore._collection_name_for_scenario("BANK_ENTERPRISE", "bge_small")
        == "rule_chunks_bank_enterprise_bge_small"
    )
    assert (
        ChromaRuleStore._collection_name_for_scenario("BANK_ENTERPRISE", "bge_m3")
        == "rule_chunks_bank_enterprise_bge_m3"
    )


def test_rebuild_indexes_rebuilds_both_scenarios_idempotently(tmp_path: Path) -> None:
    chunks_path = _build_scenario_chunks(tmp_path)
    store = ChromaRuleStore(
        chunks_path=chunks_path,
        chroma_path=tmp_path / "chroma",
        embedding_backend="hash",
    )

    first_counts = store.rebuild_indexes()
    second_counts = store.rebuild_indexes()

    assert first_counts == second_counts
    assert first_counts["BANK_ENTERPRISE"] > 0
    assert first_counts["BANK_CLEARING"] > 0
    assert store.collection("BANK_ENTERPRISE").count() == first_counts["BANK_ENTERPRISE"]
    assert store.collection("BANK_CLEARING").count() == first_counts["BANK_CLEARING"]


def test_different_backends_use_independent_collections(
    tmp_path: Path,
    monkeypatch,
) -> None:
    chunks_path = _build_scenario_chunks(tmp_path)
    chroma_path = tmp_path / "chroma"
    monkeypatch.setattr(
        retriever,
        "build_embedding_function",
        lambda backend: retriever.HashEmbeddingFunction(),
    )

    for backend in ("hash", "bge_small", "bge_m3"):
        ChromaRuleStore(
            chunks_path=chunks_path,
            chroma_path=chroma_path,
            embedding_backend=backend,
        ).rebuild_indexes(scenarios=("BANK_ENTERPRISE",))

    client = chromadb.PersistentClient(path=str(chroma_path))
    collection_names = {collection.name for collection in client.list_collections()}

    assert {
        "rule_chunks_bank_enterprise_hash",
        "rule_chunks_bank_enterprise_bge_small",
        "rule_chunks_bank_enterprise_bge_m3",
    } <= collection_names


def test_eval_rag_cli_passes_embedding_backend_to_retriever(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured_backends: list[str | None] = []

    class FakeStore:
        def __init__(self, **kwargs) -> None:
            captured_backends.append(kwargs["embedding_backend"])

    class FakeRetriever:
        def __init__(self, *, store) -> None:
            self.store = store

    monkeypatch.setattr(eval_rag, "ChromaRuleStore", FakeStore)
    monkeypatch.setattr(eval_rag, "RuleRetriever", FakeRetriever)
    monkeypatch.setattr(eval_rag, "load_eval_set", lambda path: [])
    monkeypatch.setattr(
        eval_rag,
        "evaluate_eval_set",
        lambda cases, *, retriever, top_k: {
            "case_count": 0,
            "notes": [],
            "summaries": [],
            "results": [],
        },
    )

    eval_rag.main(
        [
            "--eval-set",
            str(tmp_path / "missing.json"),
            "--chroma",
            str(tmp_path / "chroma"),
            "--embedding-backend",
            "bge_small",
            "--report",
            str(tmp_path / "report.md"),
            "--json-report",
            str(tmp_path / "report.json"),
        ]
    )

    assert captured_backends == ["bge_small"]
