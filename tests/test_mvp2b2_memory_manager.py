import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from bank_reconciliation_agent.core.llm.provider import LLMResult
from bank_reconciliation_agent.services.memory.long_term import LongTermMemoryService
from bank_reconciliation_agent.services.memory.manager import MemoryManager
from bank_reconciliation_agent.services.memory.short_term import ShortTermMemoryService
from bank_reconciliation_agent.services.memory.summary import SummaryMemoryService


class SummaryProvider:
    def __init__(self, text: str) -> None:
        self._text = text

    def complete(self, messages, *, temperature=0.0, response_format="json_object") -> LLMResult:
        del messages, temperature, response_format
        return LLMResult(
            text=json.dumps({"summary_text": self._text}, ensure_ascii=False),
            prompt_tokens=120,
            completion_tokens=60,
            model="summary-test",
        )


class FailingSummaryProvider:
    def complete(self, messages, *, temperature=0.0, response_format="json_object") -> LLMResult:
        del messages, temperature, response_format
        raise RuntimeError("summary provider unavailable")


def test_memory_manager_returns_empty_string_when_memory_is_empty() -> None:
    manager = MemoryManager()

    context = manager.build_context(
        user_id=f"memory-user-empty-{uuid4().hex}",
        thread_id=f"thread-empty-{uuid4().hex}",
        error_type="AMOUNT_MISMATCH",
        current_item={},
    )

    assert context == ""


def test_memory_manager_builds_context_in_layer_order_and_truncates() -> None:
    suffix = uuid4().hex
    user_id = f"memory-user-manager-{suffix}"
    thread_id = f"thread-manager-{suffix}"
    now = datetime.utcnow()
    long_term = LongTermMemoryService()
    short_term = ShortTermMemoryService()
    summary = SummaryMemoryService()
    manager = MemoryManager(
        long_term_service=long_term,
        short_term_service=short_term,
        summary_service=summary,
        long_term_token_budget=13,
        short_term_token_budget=16,
        summary_token_budget=12,
    )

    long_term.append(
        user_id=user_id,
        error_type="AMOUNT_MISMATCH",
        exception_branch="BC-R001",
        flow_id="FLOW-LONG-1",
        bank_amount=Decimal("100.00"),
        clear_amount=Decimal("90.00"),
        amount_diff=Decimal("10.00"),
        summary_keywords=["amount", "fee"],
        human_decision="APPROVED",
        ai_suggestion="PENDING_HUMAN",
        ai_confidence=Decimal("0.82"),
    )
    long_term.append(
        user_id=user_id,
        error_type="AMOUNT_MISMATCH",
        exception_branch="BC-R002",
        flow_id="FLOW-LONG-2",
        bank_amount=Decimal("500.00"),
        clear_amount=Decimal("400.00"),
        amount_diff=Decimal("100.00"),
        summary_keywords=["amount", "large", "invoice"],
        human_decision="REJECTED",
        ai_suggestion="PENDING_HUMAN",
        ai_confidence=Decimal("0.75"),
    )
    short_term.append(
        thread_id=thread_id,
        queue_id=901,
        error_type="AMOUNT_MISMATCH",
        decision="PENDING_HUMAN",
        confidence=Decimal("0.66"),
        expires_at=now + timedelta(hours=1),
    )
    summary.upsert(
        thread_id=thread_id,
        summary_text="Summary keeps high risk amount cases for this thread",
        compressed_count=20,
        last_compressed_at=now,
    )

    context = manager.build_context(
        user_id=user_id,
        thread_id=thread_id,
        error_type="AMOUNT_MISMATCH",
        current_item={
            "amount_diff": "100.00",
            "summary": "large invoice amount mismatch fee",
        },
    )

    assert context.index("Long-term memory") < context.index("Short-term memory")
    assert context.index("Short-term memory") < context.index("Summary memory")
    assert "FLOW-LONG-2" in context
    assert "FLOW-LONG-1" not in context
    assert "queue_id=901" in context
    assert "Summary keeps high risk" in context
    assert len(context.split()) <= 52


def test_memory_manager_build_context_uses_query_keywords_for_recall_ranking() -> None:
    suffix = uuid4().hex
    user_id = f"memory-user-nested-{suffix}"
    thread_id = f"thread-nested-{suffix}"
    long_term = LongTermMemoryService()
    manager = MemoryManager(long_term_service=long_term)

    long_term.append(
        user_id=user_id,
        error_type="AMOUNT_MISMATCH",
        exception_branch="BC-R001",
        flow_id="FLOW-BEST-MATCH",
        bank_amount=Decimal("30000.00"),
        clear_amount=Decimal("15000.00"),
        amount_diff=Decimal("15000.00"),
        summary_keywords=["amount_mismatch", "amount_large", "冲正退款", "客户名不一致"],
        human_decision="APPROVED",
        ai_suggestion="PENDING_HUMAN",
        ai_confidence=Decimal("0.91"),
    )
    long_term.append(
        user_id=user_id,
        error_type="AMOUNT_MISMATCH",
        exception_branch="BC-R002",
        flow_id="FLOW-WEAKER-MATCH",
        bank_amount=Decimal("200.00"),
        clear_amount=Decimal("150.00"),
        amount_diff=Decimal("50.00"),
        summary_keywords=["amount_mismatch", "amount_small", "手续费重复"],
        human_decision="REJECTED",
        ai_suggestion="PENDING_HUMAN",
        ai_confidence=Decimal("0.76"),
    )

    context = manager.build_context(
        user_id=user_id,
        thread_id=thread_id,
        error_type="AMOUNT_MISMATCH",
        current_item={
            "amount_diff": "15000.00",
            "summary": "冲正退款 客户名不一致",
            "remark": "原流水冲正",
        },
    )

    assert "FLOW-BEST-MATCH" in context
    assert "FLOW-WEAKER-MATCH" in context
    assert context.index("FLOW-BEST-MATCH") < context.index("FLOW-WEAKER-MATCH")


def test_update_after_decision_writes_short_term_only_before_human_confirmation() -> None:
    suffix = uuid4().hex
    user_id = f"memory-user-update-{suffix}"
    thread_id = f"thread-update-{suffix}"
    long_term = LongTermMemoryService()
    short_term = ShortTermMemoryService()
    manager = MemoryManager(
        long_term_service=long_term,
        short_term_service=short_term,
    )

    manager.update_after_decision(
        user_id=user_id,
        thread_id=thread_id,
        error_type="AMOUNT_MISMATCH",
        decision={
            "queue_id": 1201,
            "flow_id": "FLOW-SHORT-ONLY",
            "decision": "PENDING_HUMAN",
            "confidence": 0.83,
            "exception_branch": "BE-R002",
            "bank_amount": "300.00",
            "clear_amount": "295.00",
            "amount_diff": "5.00",
            "ai_suggestion": "PENDING_HUMAN",
            "reason": "金额差异待人工确认",
        },
        is_human_confirmed=False,
    )

    short_rows = short_term.recent(thread_id=thread_id)
    long_rows = long_term.recall(
        user_id=user_id,
        error_type="AMOUNT_MISMATCH",
        keywords=["amount"],
    )

    assert len(short_rows) == 1
    assert short_rows[0]["queue_id"] == 1201
    assert short_rows[0]["decision"] == "PENDING_HUMAN"
    assert short_rows[0]["confidence"] == Decimal("0.8300")
    assert short_rows[0]["expires_at"] > datetime.utcnow() + timedelta(hours=23)
    assert long_rows == []


def test_update_after_decision_writes_long_term_after_human_confirmation() -> None:
    suffix = uuid4().hex
    user_id = f"memory-user-confirmed-{suffix}"
    thread_id = f"thread-confirmed-{suffix}"
    long_term = LongTermMemoryService()
    short_term = ShortTermMemoryService()
    manager = MemoryManager(
        long_term_service=long_term,
        short_term_service=short_term,
    )

    manager.update_after_decision(
        user_id=user_id,
        thread_id=thread_id,
        error_type="AMOUNT_MISMATCH",
        decision={
            "queue_id": 1202,
            "flow_id": "FLOW-LONG-ONLY",
            "decision": "FIXED",
            "confidence": Decimal("0.9200"),
            "exception_branch": "BE-R002",
            "bank_amount": "300.00",
            "clear_amount": "295.00",
            "amount_diff": "5.00",
            "ai_suggestion": "PENDING_HUMAN",
            "human_decision": "APPROVED_MATCH",
            "summary": "invoice amount mismatch resolved by human reviewer",
            "remark": "confirmed by ops",
        },
        is_human_confirmed=True,
    )

    short_rows = short_term.recent(thread_id=thread_id)
    long_rows = long_term.recall(
        user_id=user_id,
        error_type="AMOUNT_MISMATCH",
        keywords=["invoice", "confirmed"],
    )

    assert short_rows == []
    assert len(long_rows) == 1
    assert long_rows[0]["flow_id"] == "FLOW-LONG-ONLY"
    assert long_rows[0]["human_decision"] == "APPROVED_MATCH"
    assert long_rows[0]["ai_suggestion"] == "PENDING_HUMAN"
    assert long_rows[0]["summary_keywords"][:3] == ["amount_mismatch", "amount_small", "invoice"]


def test_update_after_decision_compacts_twenty_short_term_rows_into_summary(tmp_path: Path) -> None:
    thread_id = f"thread-summary-success-{uuid4().hex}"
    summary_service = SummaryMemoryService()
    short_term = ShortTermMemoryService()
    manager = MemoryManager(
        short_term_service=short_term,
        summary_service=summary_service,
        llm_provider=SummaryProvider(
            "HIGH flow_id=FLOW-0001 kept; pending flow_id=FLOW-0002 kept; "
            "flow_id=FLOW-0003 flow_id=FLOW-0004 flow_id=FLOW-0005 flow_id=FLOW-0006 "
            "flow_id=FLOW-0007 flow_id=FLOW-0008 flow_id=FLOW-0009 flow_id=FLOW-0010 "
            "flow_id=FLOW-0011 flow_id=FLOW-0012 flow_id=FLOW-0013 flow_id=FLOW-0014 "
            "flow_id=FLOW-0015 flow_id=FLOW-0016"
        ),
        snapshot_dir=tmp_path,
    )

    for index in range(20):
        manager.update_after_decision(
            user_id="demo_user",
            thread_id=thread_id,
            error_type="AMOUNT_MISMATCH",
            decision={
                "queue_id": 2000 + index,
                "flow_id": f"FLOW-{index + 1:04d}",
                "decision": "PENDING_HUMAN",
                "risk_level": "HIGH" if index == 0 else "MEDIUM",
                "confidence": Decimal("0.8800"),
                "summary": f"case {index + 1}",
            },
            is_human_confirmed=False,
        )

    summary = summary_service.get(thread_id=thread_id)
    snapshot_files = list(tmp_path.glob(f"{thread_id}-*.json"))

    assert summary is not None
    assert summary["compressed_count"] == 20
    assert "FLOW-0001" in summary["summary_text"]
    assert len(snapshot_files) == 1
    snapshot_rows = json.loads(snapshot_files[0].read_text(encoding="utf-8"))
    assert len(snapshot_rows) == 20
    assert snapshot_rows[0]["flow_id"] == "FLOW-0020"
    assert snapshot_rows[-1]["flow_id"] == "FLOW-0001"


def test_update_after_decision_compacts_when_twenty_unexpired_rows_exist(tmp_path: Path) -> None:
    thread_id = f"thread-summary-unexpired-{uuid4().hex}"
    summary_service = SummaryMemoryService()
    short_term = ShortTermMemoryService()
    manager = MemoryManager(
        short_term_service=short_term,
        summary_service=summary_service,
        llm_provider=SummaryProvider(
            "HIGH flow_id=FLOW-0001 kept; pending flow_id=FLOW-0002 kept; "
            "flow_id=FLOW-0003 flow_id=FLOW-0004 flow_id=FLOW-0005 flow_id=FLOW-0006 "
            "flow_id=FLOW-0007 flow_id=FLOW-0008 flow_id=FLOW-0009 flow_id=FLOW-0010 "
            "flow_id=FLOW-0011 flow_id=FLOW-0012 flow_id=FLOW-0013 flow_id=FLOW-0014 "
            "flow_id=FLOW-0015 flow_id=FLOW-0016"
        ),
        snapshot_dir=tmp_path,
    )

    now = datetime.utcnow()
    short_term.append(
        thread_id=thread_id,
        queue_id=4999,
        flow_id="FLOW-EXPIRED",
        error_type="AMOUNT_MISMATCH",
        risk_level="LOW",
        decision="PENDING_HUMAN",
        confidence=Decimal("0.1000"),
        expires_at=now - timedelta(hours=1),
    )
    for index in range(19):
        short_term.append(
            thread_id=thread_id,
            queue_id=5100 + index,
            flow_id=f"FLOW-{index + 1:04d}",
            error_type="AMOUNT_MISMATCH",
            risk_level="HIGH" if index == 0 else "MEDIUM",
            decision="PENDING_HUMAN",
            confidence=Decimal("0.8800"),
            expires_at=now + timedelta(hours=1),
        )

    manager.update_after_decision(
        user_id="demo_user",
        thread_id=thread_id,
        error_type="AMOUNT_MISMATCH",
        decision={
            "queue_id": 5119,
            "flow_id": "FLOW-0020",
            "decision": "PENDING_HUMAN",
            "risk_level": "MEDIUM",
            "confidence": Decimal("0.8800"),
            "summary": "case 20",
        },
        is_human_confirmed=False,
    )

    summary = summary_service.get(thread_id=thread_id)

    assert summary is not None
    assert summary["compressed_count"] == 20
    assert "FLOW-0001" in summary["summary_text"]


def test_update_after_decision_rejects_summary_missing_high_rows(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    thread_id = f"thread-summary-fail-{uuid4().hex}"
    summary_service = SummaryMemoryService()
    short_term = ShortTermMemoryService()
    manager = MemoryManager(
        short_term_service=short_term,
        summary_service=summary_service,
        llm_provider=SummaryProvider(
            "Only pending flow_id=FLOW-0002 is kept; "
            "flow_id=FLOW-0003 flow_id=FLOW-0004 flow_id=FLOW-0005 flow_id=FLOW-0006 "
            "flow_id=FLOW-0007 flow_id=FLOW-0008 flow_id=FLOW-0009 flow_id=FLOW-0010 "
            "flow_id=FLOW-0011 flow_id=FLOW-0012 flow_id=FLOW-0013 flow_id=FLOW-0014 "
            "flow_id=FLOW-0015 flow_id=FLOW-0016"
        ),
        snapshot_dir=tmp_path,
    )

    with caplog.at_level("WARNING"):
        for index in range(20):
            manager.update_after_decision(
                user_id="demo_user",
                thread_id=thread_id,
                error_type="AMOUNT_MISMATCH",
                decision={
                    "queue_id": 3000 + index,
                    "flow_id": f"FLOW-{index + 1:04d}",
                    "decision": "PENDING_HUMAN",
                    "risk_level": "HIGH" if index == 0 else "MEDIUM",
                    "confidence": Decimal("0.8800"),
                    "summary": f"case {index + 1}",
                },
                is_human_confirmed=False,
            )

    assert summary_service.get(thread_id=thread_id) is None
    assert "memory_summary_validation_failed" in caplog.text


def test_update_after_decision_keeps_working_when_summary_compaction_fails(tmp_path: Path) -> None:
    thread_id = f"thread-summary-degrade-{uuid4().hex}"
    summary_service = SummaryMemoryService()
    short_term = ShortTermMemoryService()
    manager = MemoryManager(
        short_term_service=short_term,
        summary_service=summary_service,
        llm_provider=FailingSummaryProvider(),
        snapshot_dir=tmp_path,
    )

    for index in range(20):
        manager.update_after_decision(
            user_id="demo_user",
            thread_id=thread_id,
            error_type="AMOUNT_MISMATCH",
            decision={
                "queue_id": 4000 + index,
                "flow_id": f"FLOW-{index + 1:04d}",
                "decision": "PENDING_HUMAN",
                "risk_level": "MEDIUM",
                "confidence": Decimal("0.8800"),
                "summary": f"case {index + 1}",
            },
            is_human_confirmed=False,
        )

    assert len(short_term.recent(thread_id=thread_id, limit=25)) == 20
    assert summary_service.get(thread_id=thread_id) is None
