from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from bank_reconciliation_agent.main import app
from bank_reconciliation_agent.services.memory.long_term import LongTermMemoryService
from bank_reconciliation_agent.services.memory.short_term import ShortTermMemoryService
from bank_reconciliation_agent.services.memory.summary import SummaryMemoryService
from tests.auth_helpers import demo_bearer_headers


client = TestClient(app)
DEMO_HEADERS = demo_bearer_headers()


def test_get_memory_context_returns_aggregated_layers() -> None:
    thread_id = f"thread-memory-api-{uuid4().hex}"
    short_term_service = ShortTermMemoryService()
    long_term_service = LongTermMemoryService()
    summary_service = SummaryMemoryService()

    short_term_service.append(
        thread_id=thread_id,
        queue_id=101,
        flow_id="FLOW-101",
        error_type="AMOUNT_MISMATCH",
        risk_level="MEDIUM",
        decision="PENDING_HUMAN",
        confidence=Decimal("0.8100"),
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    short_term_service.append(
        thread_id=thread_id,
        queue_id=102,
        flow_id="FLOW-102",
        error_type="AMOUNT_MISMATCH",
        risk_level="LOW",
        decision="AUTO_FIXED",
        confidence=Decimal("0.9200"),
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    summary_service.upsert(
        thread_id=thread_id,
        summary_text="最近两笔金额差异多为人工复核后确认。",
        compressed_count=2,
        last_compressed_at=datetime.utcnow(),
    )
    long_term_service.append(
        user_id="demo_user",
        error_type="AMOUNT_MISMATCH",
        exception_branch="BE-R002",
        flow_id="FLOW-LONG-1",
        bank_amount=Decimal("100.00"),
        clear_amount=Decimal("99.00"),
        amount_diff=Decimal("1.00"),
        summary_keywords=["amount_mismatch", "客户", "退款"],
        human_decision="APPROVED_MATCH",
        ai_suggestion="PENDING_HUMAN",
        ai_confidence=Decimal("0.7500"),
    )
    long_term_service.append(
        user_id="demo_user",
        error_type="AMOUNT_MISMATCH",
        exception_branch="BE-R002",
        flow_id="FLOW-LONG-2",
        bank_amount=Decimal("300.00"),
        clear_amount=Decimal("299.00"),
        amount_diff=Decimal("1.00"),
        summary_keywords=["amount_mismatch", "客户", "手续费"],
        human_decision="APPROVED_MATCH",
        ai_suggestion="PENDING_HUMAN",
        ai_confidence=Decimal("0.9500"),
    )

    response = client.get(
        f"/api/v1/memory/demo_user/context?thread_id={thread_id}&error_type=AMOUNT_MISMATCH",
        headers=DEMO_HEADERS,
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["short_term"] == {
        "recent_decisions": 2,
        "summary": "最近两笔金额差异多为人工复核后确认。",
    }
    assert body["long_term"] == {
        "similar_cases": 2,
        "historical_pattern": "APPROVED_MATCH",
        "avg_confidence": 0.85,
    }


def test_get_memory_context_returns_empty_defaults_when_memory_missing() -> None:
    error_type = f"ERROR_TYPE_{uuid4().hex}"
    response = client.get(
        f"/api/v1/memory/demo_user/context?thread_id=thread-empty-{uuid4().hex}&error_type={error_type}",
        headers=DEMO_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "short_term": {"recent_decisions": 0, "summary": None},
        "long_term": {"similar_cases": 0, "historical_pattern": None, "avg_confidence": None},
    }


def test_get_memory_context_rejects_cross_user_query() -> None:
    response = client.get(
        "/api/v1/memory/other_user/context?thread_id=thread-1&error_type=AMOUNT_MISMATCH",
        headers=DEMO_HEADERS,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden user access"
