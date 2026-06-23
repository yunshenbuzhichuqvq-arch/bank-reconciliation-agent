from __future__ import annotations

from decimal import Decimal

from sqlalchemy import create_engine, inspect, select

from bank_reconciliation_agent.agents.audit_agent import AuditDecision
from bank_reconciliation_agent.rag.scoring import representative_score
from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchResponse
from bank_reconciliation_agent.services.fallback import l1_requires_l2
from bank_reconciliation_agent.services.rag_log import RagLogService, rag_retrieval_log_table


def test_rag_log_schema_and_schema_sql_define_same_hybrid_columns() -> None:
    engine = create_engine("sqlite:///:memory:")
    rag_retrieval_log_table.metadata.create_all(engine, tables=[rag_retrieval_log_table])

    inspector = inspect(engine)
    actual_columns = {column["name"] for column in inspector.get_columns("t_rag_retrieval_log")}

    expected_columns = {
        "rewritten_query",
        "dense_score",
        "bm25_score",
        "reranker_score",
        "fusion_rank",
        "selected_chunk_id",
    }

    assert expected_columns <= actual_columns

    schema_sql = read_schema_sql()
    for fragment in [
        "rewritten_query TEXT DEFAULT NULL",
        "dense_score DECIMAL(8,4) DEFAULT NULL",
        "bm25_score DECIMAL(8,4) DEFAULT NULL",
        "reranker_score DECIMAL(8,4) DEFAULT NULL",
        "fusion_rank INT DEFAULT NULL",
        "selected_chunk_id VARCHAR(128) DEFAULT NULL",
    ]:
        assert fragment in schema_sql


def test_rag_log_build_row_persists_hybrid_fields_and_rewritten_query() -> None:
    engine = create_engine("sqlite:///:memory:")
    service = RagLogService(engine)
    item = _item(
        score=0.91,
        dense_score=Decimal("0.62"),
        bm25_score=Decimal("8.50"),
        reranker_score=Decimal("0.91"),
        fusion_rank=2,
    )
    row = service.build_row(
        user_id="demo_user",
        task_id="TASK-RAG-001",
        query_text="金额差异",
        top_k=5,
        items=[item],
        response=RagSearchResponse(items=[item], rewritten_query="金额差异 对账 规则"),
    )

    service.replace_task_rows(user_id="demo_user", task_id="TASK-RAG-001", rows=[row])

    with engine.connect() as connection:
        persisted = connection.execute(select(rag_retrieval_log_table)).mappings().one()

    assert persisted["best_score"] == Decimal("0.9100")
    assert persisted["selected_chunk_id"] == "rule-001"
    assert persisted["rewritten_query"] == "金额差异 对账 规则"
    assert persisted["dense_score"] == Decimal("0.6200")
    assert persisted["bm25_score"] == Decimal("8.5000")
    assert persisted["reranker_score"] == Decimal("0.9100")
    assert persisted["fusion_rank"] == 2


def test_representative_score_prefers_reranker_then_dense_when_hybrid_missing() -> None:
    reranked = _item(score=0.40, dense_score=Decimal("0.61"), reranker_score=Decimal("0.83"))
    dense_only = _item(score=0.40, dense_score=Decimal("0.61"))
    empty = _item(score=0.40)

    assert representative_score(reranked) == 0.83
    assert representative_score(dense_only) == 0.61
    assert representative_score(empty) == 0.4


def test_fallback_uses_only_audit_confidence() -> None:
    assert l1_requires_l2(_decision(confidence=0.90)) is False
    assert l1_requires_l2(_decision(confidence=0.40)) is True


def _decision(*, confidence: float) -> AuditDecision:
    return AuditDecision(
        flow_id="FLOW-001",
        decision="PENDING_HUMAN",
        risk_level="MEDIUM",
        reason="reason",
        ai_suggestion="PENDING_HUMAN",
        evidence=[],
        confidence=confidence,
        fallback_applied=False,
        fallback_level=0,
        next_action="PENDING_HUMAN",
    )


def _item(
    *,
    score: float,
    dense_score: Decimal | None = None,
    bm25_score: Decimal | None = None,
    reranker_score: Decimal | None = None,
    fusion_rank: int | None = None,
) -> RagSearchItem:
    return RagSearchItem(
        chunk_id="rule-001",
        source="rules.md#rule",
        source_name="规则",
        source_url="https://example.com/rule",
        source_file="rules.md",
        section_title="rule",
        element_type="paragraph",
        business_tags=["bank_enterprise"],
        score=score,
        content="规则证据",
        dense_score=float(dense_score) if dense_score is not None else None,
        bm25_score=float(bm25_score) if bm25_score is not None else None,
        reranker_score=float(reranker_score) if reranker_score is not None else None,
        fusion_rank=fusion_rank,
    )


def read_schema_sql() -> str:
    return open("src/bank_reconciliation_agent/db/schema.sql", encoding="utf-8").read()
