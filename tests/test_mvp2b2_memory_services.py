from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import inspect

from bank_reconciliation_agent.services.memory.engine import get_memory_engine
from bank_reconciliation_agent.services.memory.long_term import LongTermMemoryService
from bank_reconciliation_agent.services.memory.short_term import ShortTermMemoryService
from bank_reconciliation_agent.services.memory.summary import SummaryMemoryService


def test_short_term_memory_round_trip_filters_expired_and_purges() -> None:
    service = ShortTermMemoryService()
    suffix = uuid4().hex
    thread_id = f"thread-2b2-short-{suffix}"
    now = datetime.utcnow()

    service.append(
        thread_id=thread_id,
        queue_id=101,
        error_type="AMOUNT_MISMATCH",
        decision="AUTO_PASS",
        confidence=Decimal("0.91"),
        expires_at=now + timedelta(hours=1),
    )
    service.append(
        thread_id=thread_id,
        queue_id=102,
        error_type="TIME_DIFF",
        decision="PENDING_HUMAN",
        confidence=Decimal("0.42"),
        expires_at=now - timedelta(hours=1),
    )
    service.append(
        thread_id=f"other-thread-2b2-short-{suffix}",
        queue_id=103,
        error_type="AMOUNT_MISMATCH",
        decision="AUTO_REJECT",
        confidence=Decimal("0.11"),
        expires_at=now + timedelta(hours=1),
    )

    recent = service.recent(thread_id=thread_id)

    assert [row["queue_id"] for row in recent] == [101]
    assert recent[0]["confidence"] == Decimal("0.91")
    assert service.count(thread_id=thread_id) == 1
    assert service.purge_expired() >= 1
    assert service.count(thread_id=thread_id) == 1


def test_long_term_memory_append_and_recall_are_user_and_error_type_isolated() -> None:
    service = LongTermMemoryService()
    suffix = uuid4().hex
    user_a = f"memory-user-a-{suffix}"
    user_b = f"memory-user-b-{suffix}"

    service.append(
        user_id=user_a,
        error_type="AMOUNT_MISMATCH",
        exception_branch="BC-R001",
        flow_id="FLOW-001",
        bank_amount=Decimal("100.00"),
        clear_amount=Decimal("90.00"),
        amount_diff=Decimal("10.00"),
        summary_keywords=["amount", "fee"],
        human_decision="APPROVED",
        ai_suggestion="PENDING_HUMAN",
        ai_confidence=Decimal("0.80"),
    )
    service.append(
        user_id=user_b,
        error_type="AMOUNT_MISMATCH",
        exception_branch="BC-R001",
        flow_id="FLOW-002",
        bank_amount=Decimal("200.00"),
        clear_amount=Decimal("190.00"),
        amount_diff=Decimal("10.00"),
        summary_keywords=["amount"],
        human_decision="REJECTED",
        ai_suggestion="PENDING_HUMAN",
        ai_confidence=Decimal("0.70"),
    )
    service.append(
        user_id=user_a,
        error_type="TIME_DIFF",
        exception_branch="BC-R003",
        flow_id="FLOW-003",
        bank_amount=Decimal("300.00"),
        clear_amount=Decimal("300.00"),
        amount_diff=Decimal("0.00"),
        summary_keywords=["time"],
        human_decision="APPROVED",
        ai_suggestion="AUTO_PASS",
        ai_confidence=Decimal("0.95"),
    )

    rows = service.recall(
        user_id=user_a,
        error_type="AMOUNT_MISMATCH",
        keywords=["amount"],
        limit=5,
    )

    assert [row["flow_id"] for row in rows] == ["FLOW-001"]
    assert rows[0]["summary_keywords"] == ["amount", "fee"]
    assert rows[0]["bank_amount"] == Decimal("100.00")


def test_long_term_memory_recall_sorts_by_keyword_overlap() -> None:
    service = LongTermMemoryService()
    user_id = f"memory-user-ranking-{uuid4().hex}"

    service.append(
        user_id=user_id,
        error_type="AMOUNT_MISMATCH",
        exception_branch="BC-R001",
        flow_id="FLOW-LOW-SCORE",
        bank_amount=Decimal("100.00"),
        clear_amount=Decimal("90.00"),
        amount_diff=Decimal("10.00"),
        summary_keywords=["amount"],
        human_decision="APPROVED",
        ai_suggestion="PENDING_HUMAN",
        ai_confidence=Decimal("0.80"),
    )
    service.append(
        user_id=user_id,
        error_type="AMOUNT_MISMATCH",
        exception_branch="BC-R001",
        flow_id="FLOW-HIGH-SCORE",
        bank_amount=Decimal("200.00"),
        clear_amount=Decimal("150.00"),
        amount_diff=Decimal("50.00"),
        summary_keywords=["amount", "invoice", "fee"],
        human_decision="REJECTED",
        ai_suggestion="PENDING_HUMAN",
        ai_confidence=Decimal("0.60"),
    )

    rows = service.recall(
        user_id=user_id,
        error_type="AMOUNT_MISMATCH",
        keywords=["amount", "invoice", "fee"],
        limit=2,
    )

    assert [row["flow_id"] for row in rows] == ["FLOW-HIGH-SCORE", "FLOW-LOW-SCORE"]


def test_summary_memory_upsert_is_idempotent_and_tables_exist() -> None:
    service = SummaryMemoryService()
    thread_id = f"thread-2b2-summary-{uuid4().hex}"
    first_time = datetime.utcnow()
    second_time = first_time + timedelta(minutes=5)

    service.upsert(
        thread_id=thread_id,
        summary_text="first summary",
        compressed_count=20,
        last_compressed_at=first_time,
    )
    service.upsert(
        thread_id=thread_id,
        summary_text="updated summary",
        compressed_count=40,
        last_compressed_at=second_time,
    )

    summary = service.get(thread_id=thread_id)
    table_names = set(inspect(get_memory_engine()).get_table_names())

    assert summary is not None
    assert summary["summary_text"] == "updated summary"
    assert summary["compressed_count"] == 40
    assert summary["last_compressed_at"] == second_time
    assert {
        "t_short_term_memory",
        "t_long_term_memory",
        "t_summary_memory",
    }.issubset(table_names)
