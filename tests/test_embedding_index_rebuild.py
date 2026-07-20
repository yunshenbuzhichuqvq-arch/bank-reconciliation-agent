import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import chromadb
import pytest
from chromadb.api.types import EmbeddingFunction

from bank_reconciliation_agent.rag import retriever
from bank_reconciliation_agent.rag.retriever import BuiltEmbeddingFunction, ChromaRuleStore
from scripts import eval_rag
from scripts.build_rule_chunks import build_rule_chunks


ROOT = Path(__file__).resolve().parents[1]


class FakeDimensionalEmbeddingFunction(EmbeddingFunction[list[str]]):
    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [[1.0, *([0.0] * (self.dimensions - 1))] for _ in input]

    @staticmethod
    def name() -> str:
        return "fake_dimensional_embedding"

    @staticmethod
    def build_from_config(config: dict) -> "FakeDimensionalEmbeddingFunction":
        return FakeDimensionalEmbeddingFunction(int(config["dimensions"]))

    def get_config(self) -> dict:
        return {"dimensions": self.dimensions}


class CountingEmbeddingFunction(EmbeddingFunction[list[str]]):
    def __init__(self) -> None:
        self.encoded_texts = 0

    def __call__(self, input: list[str]) -> list[list[float]]:
        self.encoded_texts += len(input)
        return [[1.0, 0.0] for _ in input]

    @staticmethod
    def name() -> str:
        return "counting_embedding"

    @staticmethod
    def build_from_config(config: dict) -> "CountingEmbeddingFunction":
        del config
        return CountingEmbeddingFunction()

    def get_config(self) -> dict:
        return {"dimensions": 2}


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


def _write_two_chunks(tmp_path: Path) -> Path:
    source_chunks = [
        json.loads(line)
        for line in (ROOT / "data/rag/rule_chunks_bank_enterprise.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[:2]
    ]
    chunks_path = tmp_path / "rule_chunks_bank_enterprise.jsonl"
    chunks_path.write_text(
        "\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in source_chunks) + "\n",
        encoding="utf-8",
    )
    return chunks_path


def _counting_store(
    *,
    chunks_path: Path,
    chroma_path: Path,
    embedding: CountingEmbeddingFunction,
    monkeypatch,
) -> ChromaRuleStore:
    monkeypatch.setattr(
        retriever,
        "build_embedding_function",
        lambda backend: BuiltEmbeddingFunction(embedding, backend),
    )
    return ChromaRuleStore(
        chunks_path=chunks_path,
        chroma_path=chroma_path,
        embedding_backend="hash",
    )


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


def test_same_source_fingerprint_skips_reembedding(
    tmp_path: Path,
    monkeypatch,
) -> None:
    chunks_path = _write_two_chunks(tmp_path)
    chroma_path = tmp_path / "chroma"
    first_embedding = CountingEmbeddingFunction()
    first_store = _counting_store(
        chunks_path=chunks_path,
        chroma_path=chroma_path,
        embedding=first_embedding,
        monkeypatch=monkeypatch,
    )
    assert first_store.warmup() == 2
    assert first_embedding.encoded_texts == 2

    second_embedding = CountingEmbeddingFunction()
    second_store = _counting_store(
        chunks_path=chunks_path,
        chroma_path=chroma_path,
        embedding=second_embedding,
        monkeypatch=monkeypatch,
    )

    assert second_store.warmup() == 2
    assert second_embedding.encoded_texts == 0


def test_legacy_matching_collection_adds_marker_without_reembedding(
    tmp_path: Path,
    monkeypatch,
) -> None:
    chunks_path = _write_two_chunks(tmp_path)
    chunks = [json.loads(line) for line in chunks_path.read_text(encoding="utf-8").splitlines()]
    chroma_path = tmp_path / "chroma"
    legacy_embedding = CountingEmbeddingFunction()
    metadata_store = ChromaRuleStore(
        chunks_path=chunks_path,
        chroma_path=chroma_path,
        embedding_backend="hash",
    )
    legacy_collection = chromadb.PersistentClient(path=str(chroma_path)).get_or_create_collection(
        name="rule_chunks_bank_enterprise_hash",
        embedding_function=legacy_embedding,
    )
    legacy_collection.upsert(
        ids=[chunk["chunk_id"] for chunk in chunks],
        documents=[chunk["content"] for chunk in chunks],
        metadatas=[metadata_store._to_metadata(chunk) for chunk in chunks],
    )
    assert legacy_embedding.encoded_texts == 2

    warm_embedding = CountingEmbeddingFunction()
    store = _counting_store(
        chunks_path=chunks_path,
        chroma_path=chroma_path,
        embedding=warm_embedding,
        monkeypatch=monkeypatch,
    )
    collection = store.collection()

    assert warm_embedding.encoded_texts == 0
    assert retriever.COLLECTION_FINGERPRINT_KEY in (collection.metadata or {})


def test_same_count_changed_source_reembeds(
    tmp_path: Path,
    monkeypatch,
) -> None:
    chunks_path = _write_two_chunks(tmp_path)
    chroma_path = tmp_path / "chroma"
    first_store = _counting_store(
        chunks_path=chunks_path,
        chroma_path=chroma_path,
        embedding=CountingEmbeddingFunction(),
        monkeypatch=monkeypatch,
    )
    assert first_store.warmup() == 2

    chunks = [json.loads(line) for line in chunks_path.read_text(encoding="utf-8").splitlines()]
    chunks[0]["content"] += " source changed"
    chunks_path.write_text(
        "\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n",
        encoding="utf-8",
    )
    changed_embedding = CountingEmbeddingFunction()
    changed_store = _counting_store(
        chunks_path=chunks_path,
        chroma_path=chroma_path,
        embedding=changed_embedding,
        monkeypatch=monkeypatch,
    )

    assert changed_store.warmup() == 2
    assert changed_embedding.encoded_texts == 2


def test_concurrent_warmup_initializes_collection_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = ChromaRuleStore(
        chunks_path=_write_two_chunks(tmp_path),
        chroma_path=tmp_path / "chroma",
        embedding_backend="hash",
    )
    original = store._ensure_collection_synced
    initialize_calls = 0

    def counted_initialize(collection, *, scenario_type):
        nonlocal initialize_calls
        initialize_calls += 1
        time.sleep(0.02)
        return original(collection, scenario_type=scenario_type)

    monkeypatch.setattr(store, "_ensure_collection_synced", counted_initialize)
    with ThreadPoolExecutor(max_workers=4) as executor:
        counts = list(executor.map(lambda _: store.warmup(), range(4)))

    assert counts == [2, 2, 2, 2]
    assert initialize_calls == 1


def test_failed_warmup_is_not_cached_and_can_retry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = ChromaRuleStore(
        chunks_path=_write_two_chunks(tmp_path),
        chroma_path=tmp_path / "chroma",
        embedding_backend="hash",
    )
    original = store._ensure_collection_synced
    initialize_calls = 0

    def fail_once(collection, *, scenario_type):
        nonlocal initialize_calls
        initialize_calls += 1
        if initialize_calls == 1:
            raise RuntimeError("temporary initialization failure")
        return original(collection, scenario_type=scenario_type)

    monkeypatch.setattr(store, "_ensure_collection_synced", fail_once)

    with pytest.raises(RuntimeError, match="temporary initialization failure"):
        store.warmup()
    assert store._collections == {}
    assert store.warmup() == 2
    assert initialize_calls == 2


def test_different_backends_use_independent_collections(
    tmp_path: Path,
    monkeypatch,
) -> None:
    chunks_path = _build_scenario_chunks(tmp_path)
    chroma_path = tmp_path / "chroma"
    dimensions_by_backend = {"hash": 2, "bge_small": 3, "bge_m3": 4}

    def build_fake_embedding_function(backend: str) -> BuiltEmbeddingFunction:
        return BuiltEmbeddingFunction(
            FakeDimensionalEmbeddingFunction(dimensions_by_backend[backend]),
            backend,
        )

    monkeypatch.setattr(retriever, "build_embedding_function", build_fake_embedding_function)

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

    assert {
        collection.name: list(collection.peek(1)["embeddings"][0])
        for collection in client.list_collections()
    } == {
        "rule_chunks_bank_enterprise_hash": [1.0, 0.0],
        "rule_chunks_bank_enterprise_bge_small": [1.0, 0.0, 0.0],
        "rule_chunks_bank_enterprise_bge_m3": [1.0, 0.0, 0.0, 0.0],
    }


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
        lambda cases, *, retriever, top_k, embedding_backend, mode="dense": {
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
