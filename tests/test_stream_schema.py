from datetime import UTC, datetime

from bank_reconciliation_agent.schemas.stream import AgentStreamEvent, StreamEventType


def test_agent_stream_event_serializes_versioned_contract() -> None:
    event = AgentStreamEvent(
        event_type=StreamEventType.AGENT_DECISION,
        seq=3,
        task_id="TASK-V1-1",
        flow_id="FLOW-001",
        ts=datetime(2026, 6, 15, 10, 30, tzinfo=UTC),
        payload={
            "agent_name": "audit_agent",
            "decision": "PENDING_HUMAN",
            "confidence": 0.72,
            "fallback_level": 1,
            "prompt_version": "v1",
        },
    )

    dumped = event.model_dump()
    json_payload = event.model_dump_json()

    assert dumped["schema_version"] == "1.2"
    assert dumped["event_type"] == StreamEventType.AGENT_DECISION
    assert dumped["seq"] == 3
    assert '"event_type":"agent_decision"' in json_payload
    assert '"schema_version":"1.2"' in json_payload


def test_stream_event_contract_documents_emitted_rag_payload_and_no_dead_item_started() -> None:
    assert StreamEventType.RAG_RETRIEVED == "rag_retrieved"
    assert "item_started" not in {event_type.value for event_type in StreamEventType}

    docstring = AgentStreamEvent.__doc__ or ""
    assert "chunk_ids" in docstring
    assert "best_score" in docstring
    assert "query" in docstring
    assert "chunk_id, score, source" not in docstring


def test_v1_2_workbench_event_sample_still_validates_with_old_schema_version() -> None:
    event = AgentStreamEvent(
        schema_version="1.0",
        event_type="item_done",
        seq=7,
        task_id="TASK-V1-2",
        flow_id="FLOW-001",
        ts=datetime(2026, 6, 15, 10, 30, tzinfo=UTC),
        payload={
            "flow_id": "FLOW-001",
            "status": "PENDING_HUMAN",
            "decision": "PENDING_HUMAN",
            "confidence": 0.66,
        },
    )

    assert event.schema_version == "1.0"
    assert event.event_type == StreamEventType.ITEM_DONE


def test_task_progress_event_schema_validates_task_level_payload() -> None:
    event = AgentStreamEvent(
        event_type="task_progress",
        seq=8,
        task_id="TASK-V1-3",
        ts=datetime(2026, 6, 16, 10, 30, tzinfo=UTC),
        payload={
            "processed": 6,
            "total": 10,
            "auto_fixed": 3,
            "pending_ai": 1,
            "pending_human": 2,
            "unresolved": 0,
            "exception_dist": {"AMOUNT_MISMATCH": 2},
        },
    )

    assert event.schema_version == "1.2"
    assert event.event_type == StreamEventType.TASK_PROGRESS
    assert event.payload["processed"] == 6
    assert event.payload["exception_dist"] == {"AMOUNT_MISMATCH": 2}


def test_trace_span_event_serializes_canonical_safe_fields() -> None:
    event = AgentStreamEvent(
        event_type=StreamEventType.TRACE_SPAN,
        seq=5,
        task_id="TASK-TRACE-SSE",
        flow_id="FLOW-001",
        ts=datetime(2026, 6, 15, 10, 30, tzinfo=UTC),
        payload={
            "schema_version": "1.0",
            "trace_id": "trace-uuid",
            "span_id": "span-uuid",
            "span_type": "TOOL",
            "name": "search_rules",
            "sequence_no": 3,
            "status": "SUCCEEDED",
            "outcome": "RESULT",
            "duration_ms": 12,
            "attempt": 1,
            "retry_recovered": False,
            "result_count": 1,
            "evidence_ids": ["rule-001"],
        },
    )

    dumped = event.model_dump()
    assert dumped["schema_version"] == "1.2"
    assert dumped["event_type"] == StreamEventType.TRACE_SPAN
    # user_id must not leak into SSE payload.
    assert "user_id" not in dumped["payload"]
    # Canonical identity fields are present in the safe projection.
    assert dumped["payload"]["trace_id"] == "trace-uuid"
    assert dumped["payload"]["span_id"] == "span-uuid"
    assert dumped["payload"]["sequence_no"] == 3
