import json
from pathlib import Path

from fastapi.testclient import TestClient

from bank_reconciliation_agent.main import app
from bank_reconciliation_agent.rag.retriever import RuleRetriever
from bank_reconciliation_agent.schemas.rag import RagSearchRequest
from scripts.build_rule_chunks import build_rule_chunks


ROOT = Path(__file__).resolve().parents[1]


def test_build_rule_chunks_preserves_public_source_metadata(tmp_path: Path) -> None:
    output_path = tmp_path / "rule_chunks.jsonl"

    chunks = build_rule_chunks(
        sources_path=ROOT / "data/rag/sources.json",
        output_path=output_path,
    )

    assert output_path.exists()
    assert len(chunks) >= 3

    persisted_chunks = [
        json.loads(line)
        for line in output_path.read_text(encoding="utf-8").splitlines()
    ]
    assert persisted_chunks == chunks
    assert all(chunk["source_url"].startswith("https://") for chunk in chunks)
    assert all(chunk["source_file"] for chunk in chunks)
    assert all(chunk["section_title"] for chunk in chunks)
    assert all(chunk["element_type"] in {"paragraph", "table"} for chunk in chunks)

    tags = {tag for chunk in chunks for tag in chunk["business_tags"]}
    assert {"amount_mismatch", "single_side_missing", "audit_trail"} <= tags


def test_rule_retriever_searches_generated_chunks(tmp_path: Path) -> None:
    chunks_path = tmp_path / "rule_chunks.jsonl"
    build_rule_chunks(
        sources_path=ROOT / "data/rag/sources.json",
        output_path=chunks_path,
    )
    retriever = RuleRetriever(chunks_path=chunks_path)

    response = retriever.search(RagSearchRequest(query="金额差异 对账不平", top_k=2))

    assert response.items
    first_item = response.items[0]
    assert first_item.source_url.startswith("https://")
    assert first_item.source_file.endswith(".md")
    assert "amount_mismatch" in first_item.business_tags
    assert first_item.score > 0
    assert "固定结果模拟" not in first_item.content


def test_rag_search_api_returns_traceable_rule_chunks() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/rag/search",
        json={"query": "单边缺失 查询查复", "top_k": 3},
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert items
    assert any("single_side_missing" in item["business_tags"] for item in items)
    assert all(item["source_url"].startswith("https://") for item in items)
