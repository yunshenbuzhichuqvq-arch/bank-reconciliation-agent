import json
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from bank_reconciliation_agent.core.llm.provider import LLMResult
from bank_reconciliation_agent.main import app
from bank_reconciliation_agent.schemas.ledger import LedgerQuery
from bank_reconciliation_agent.services.circuit_breaker import CircuitBreaker
from bank_reconciliation_agent.services.ledger import LedgerService
from bank_reconciliation_agent.services.memory.engine import get_memory_engine
from bank_reconciliation_agent.services.memory.long_term import long_term_memory_table
from bank_reconciliation_agent.services.memory.manager import MemoryManager
from bank_reconciliation_agent.services.memory.short_term import ShortTermMemoryService
from bank_reconciliation_agent.services.memory.short_term import short_term_memory_table
from bank_reconciliation_agent.services.memory.summary import SummaryMemoryService
from bank_reconciliation_agent.services.memory.summary import summary_memory_table
from bank_reconciliation_agent.services import workflow as workflow_module
from bank_reconciliation_agent.services.reconciliation import ReconciliationService
from scripts.generate_mock_excel import (
    BANK_CLEARING_EXPECTED_BRANCHES,
    generate_mvp1_mock_excel,
    generate_mvp2a3_mock_excel,
)
from tests.auth_helpers import demo_bearer_headers


client = TestClient(app)
DEMO_HEADERS = demo_bearer_headers()


class RecordingProvider:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    def complete(self, messages, *, temperature=0.0, response_format="json_object") -> LLMResult:
        del temperature, response_format
        self.calls.append(messages)
        return LLMResult(
            text=(
                '{"decision":"PENDING_HUMAN","risk_level":"MEDIUM","reason":"记录测试",'
                '"ai_suggestion":"PENDING_HUMAN","evidence":["rule"],"confidence":0.88}'
            ),
            prompt_tokens=10,
            completion_tokens=8,
            model="recording",
        )

    def reset(self) -> None:
        self.calls.clear()


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


def test_bank_enterprise_memory_round_trip_query_api_and_reinjection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = RecordingProvider()
    task_id = f"TASK_MEMORY_BANK_{uuid4().hex[:8]}"
    _reset_memory_tables()
    monkeypatch.setattr(workflow_module.audit_agent, "provider", provider)
    monkeypatch.setattr(ReconciliationService, "_generate_task_id", lambda self, content: task_id)

    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)
    first_upload = _upload_excel_pair(bank_path, clear_path)

    assert first_upload.status_code == 200
    first_body = first_upload.json()["data"]
    assert first_body["task_id"] == task_id
    assert first_body["auto_fixed_rows"] == 2
    assert first_body["pending_human_rows"] == 6
    assert all(len(messages) == 2 for messages in provider.calls)

    queue_id = _pending_queue_id(task_id)
    approve_response = client.post(
        f"/api/v1/review/{queue_id}/approve",
        headers=DEMO_HEADERS,
        json={
            "action": "APPROVED_MATCH",
            "handler_username": "reviewer_bank",
            "remark": "memory round trip",
        },
    )

    assert approve_response.status_code == 200
    memory_context_response = client.get(
        f"/api/v1/memory/demo_user/context?thread_id={task_id}&error_type=AMOUNT_MISMATCH",
        headers=DEMO_HEADERS,
    )

    assert memory_context_response.status_code == 200
    memory_context = memory_context_response.json()["data"]
    assert memory_context["short_term"]["recent_decisions"] == 6
    assert memory_context["short_term"]["summary"] is None
    assert memory_context["long_term"]["similar_cases"] == 1
    assert memory_context["long_term"]["historical_pattern"] == "APPROVED_MATCH"
    assert 0.0 < memory_context["long_term"]["avg_confidence"] <= 1.0

    provider.reset()
    second_upload = _upload_excel_pair(bank_path, clear_path)

    assert second_upload.status_code == 200
    second_body = second_upload.json()["data"]
    assert second_body["task_id"] == task_id
    assert second_body["auto_fixed_rows"] == 2
    assert second_body["pending_human_rows"] == 6
    assert any(
        len(messages) == 3
        and "Long-term memory:" in messages[1]["content"]
        and "Short-term memory:" in messages[1]["content"]
        for messages in provider.calls
    )


def test_bank_clearing_memory_round_trip_reinjects_context_without_regression(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = RecordingProvider()
    task_id = f"TASK_MEMORY_CLEARING_{uuid4().hex[:8]}"
    expected_pending = sum(1 for _, _, disposition in BANK_CLEARING_EXPECTED_BRANCHES.values() if disposition == "PENDING_HUMAN")
    _reset_memory_tables()
    monkeypatch.setattr(workflow_module.audit_agent, "provider", provider)
    monkeypatch.setattr(ReconciliationService, "_generate_task_id", lambda self, content: task_id)

    bank_path, clear_path = generate_mvp2a3_mock_excel(tmp_path)
    first_upload = _upload_excel_pair(bank_path, clear_path, scenario_type="BANK_CLEARING")

    assert first_upload.status_code == 200
    first_body = first_upload.json()["data"]
    assert first_body["task_id"] == task_id
    assert first_body["auto_fixed_rows"] == 1
    assert first_body["pending_human_rows"] == expected_pending
    assert all(len(messages) == 2 for messages in provider.calls)

    queue_id = _pending_queue_id(task_id)
    approve_response = client.post(
        f"/api/v1/review/{queue_id}/approve",
        headers=DEMO_HEADERS,
        json={
            "action": "APPROVED_MATCH",
            "handler_username": "reviewer_clearing",
            "remark": "clearing memory round trip",
        },
    )

    assert approve_response.status_code == 200

    provider.reset()
    second_upload = _upload_excel_pair(bank_path, clear_path, scenario_type="BANK_CLEARING")

    assert second_upload.status_code == 200
    second_body = second_upload.json()["data"]
    assert second_body["task_id"] == task_id
    assert second_body["auto_fixed_rows"] == 1
    assert second_body["pending_human_rows"] == expected_pending
    assert any(
        len(messages) == 3
        and "Long-term memory:" in messages[1]["content"]
        and "Short-term memory:" in messages[1]["content"]
        for messages in provider.calls
    )


def test_memory_summary_compaction_e2e_writes_summary_after_twenty_rows(tmp_path: Path) -> None:
    thread_id = f"thread-summary-success-{uuid4().hex}"
    summary_service = SummaryMemoryService()
    short_term_service = ShortTermMemoryService()
    manager = MemoryManager(
        short_term_service=short_term_service,
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
                "queue_id": 5000 + index,
                "flow_id": f"FLOW-{index + 1:04d}",
                "decision": "PENDING_HUMAN",
                "risk_level": "HIGH" if index == 0 else "MEDIUM",
                "confidence": Decimal("0.8800"),
                "summary": f"case {index + 1}",
            },
            is_human_confirmed=False,
        )

    summary = summary_service.get(thread_id=thread_id)

    assert summary is not None
    assert summary["compressed_count"] == 20
    assert "FLOW-0001" in summary["summary_text"]


def test_memory_summary_compaction_validation_failure_degrades_without_overwriting_summary(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    thread_id = f"thread-summary-fail-{uuid4().hex}"
    summary_service = SummaryMemoryService()
    short_term_service = ShortTermMemoryService()
    manager = MemoryManager(
        short_term_service=short_term_service,
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
                    "queue_id": 6000 + index,
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


def test_rag_breaker_open_routes_upload_to_human_without_changing_baseline_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    task_id = f"TASK_BREAKER_{uuid4().hex[:8]}"
    now = 0.0

    def fake_time() -> float:
        return now

    def failing_search(request):
        del request
        raise RuntimeError("chroma unavailable")

    monkeypatch.setattr(ReconciliationService, "_generate_task_id", lambda self, content: task_id)
    monkeypatch.setattr(
        workflow_module,
        "rag_circuit_breaker",
        CircuitBreaker(fail_threshold=1, open_seconds=30, time_fn=fake_time),
    )
    monkeypatch.setattr(workflow_module.rule_retriever, "search", failing_search)

    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)
    with caplog.at_level("WARNING"):
        response = _upload_excel_pair(bank_path, clear_path)

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["task_id"] == task_id
    assert body["auto_fixed_rows"] == 2
    assert body["pending_human_rows"] == 6
    assert "rag_circuit_breaker_failure" in caplog.text
    assert "rag_circuit_breaker_open" in caplog.text

    ledger_page = LedgerService().list(
        user_id="demo_user",
        query=LedgerQuery(task_id=task_id, page=1, page_size=100),
    )

    assert ledger_page.total == 6
    assert all(row.handle_status == "PENDING_HUMAN" for row in ledger_page.items)
    assert all(row.rag_source is None for row in ledger_page.items)


def _upload_excel_pair(
    bank_path: Path,
    clear_path: Path,
    *,
    scenario_type: str | None = None,
):
    with bank_path.open("rb") as bank_file, clear_path.open("rb") as clear_file:
        return client.post(
            "/api/v1/reconcile/upload",
            headers=DEMO_HEADERS,
            data={"scenario_type": scenario_type} if scenario_type is not None else None,
            files={
                "bank_file": (
                    bank_path.name,
                    bank_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                "clear_file": (
                    clear_path.name,
                    clear_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
        )


def _pending_queue_id(task_id: str) -> int:
    response = client.get(
        f"/api/v1/review/pending?task_id={task_id}&page=1&page_size=1",
        headers=DEMO_HEADERS,
    )
    assert response.status_code == 200
    return response.json()["data"]["items"][0]["queue_id"]


def _reset_memory_tables() -> None:
    engine = get_memory_engine()
    short_term_memory_table.metadata.create_all(engine, tables=[short_term_memory_table])
    long_term_memory_table.metadata.create_all(engine, tables=[long_term_memory_table])
    summary_memory_table.metadata.create_all(engine, tables=[summary_memory_table])
    with engine.begin() as connection:
        connection.execute(short_term_memory_table.delete())
        connection.execute(long_term_memory_table.delete())
        connection.execute(summary_memory_table.delete())
