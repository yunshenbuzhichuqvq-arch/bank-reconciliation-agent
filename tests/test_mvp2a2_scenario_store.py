from pathlib import Path

from bank_reconciliation_agent.rag.retriever import ChromaRuleStore, RuleRetriever
from bank_reconciliation_agent.schemas.rag import RagSearchRequest
from scripts.build_rule_chunks import build_rule_chunks


ROOT = Path(__file__).resolve().parents[1]


def test_chroma_rule_store_defaults_to_bank_enterprise_collection_name() -> None:
    store = ChromaRuleStore(embedding_backend="hash")

    assert store.collection_name == "rule_chunks_bank_enterprise_hash"


def test_rule_retriever_search_returns_hits_for_bank_clearing_scenario(tmp_path: Path) -> None:
    bank_chunks_path = tmp_path / "rule_chunks_bank_enterprise.jsonl"
    clearing_chunks_path = tmp_path / "rule_chunks_bank_clearing.jsonl"
    build_rule_chunks(
        sources_path=ROOT / "data/rag/sources_bank_enterprise.json",
        output_path=bank_chunks_path,
    )
    build_rule_chunks(
        sources_path=ROOT / "data/rag/sources_bank_clearing.json",
        output_path=clearing_chunks_path,
    )
    retriever = RuleRetriever(chunks_path=bank_chunks_path, chroma_path=tmp_path / "chroma")

    bank_response = retriever.search(
        RagSearchRequest(
            query="金额差异 对账不平",
            top_k=2,
            scenario_type="BANK_ENTERPRISE",
        )
    )
    clearing_response = retriever.search(
        RagSearchRequest(
            query="T+1 补记 跨日切 处理",
            top_k=2,
            scenario_type="BANK_CLEARING",
        )
    )

    assert bank_response.items
    assert clearing_response.items
    assert all(
        "data/rag/raw_sources/bank_clearing/" in item.source_file
        for item in clearing_response.items
    )
