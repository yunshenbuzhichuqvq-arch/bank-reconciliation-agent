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

    assert dumped["schema_version"] == "1.0"
    assert dumped["event_type"] == StreamEventType.AGENT_DECISION
    assert dumped["seq"] == 3
    assert '"event_type":"agent_decision"' in json_payload
    assert '"schema_version":"1.0"' in json_payload


def test_stream_event_contract_documents_emitted_rag_payload_and_no_dead_item_started() -> None:
    assert StreamEventType.RAG_RETRIEVED == "rag_retrieved"
    assert "item_started" not in {event_type.value for event_type in StreamEventType}

    docstring = AgentStreamEvent.__doc__ or ""
    assert "chunk_ids" in docstring
    assert "best_score" in docstring
    assert "query" in docstring
    assert "chunk_id, score, source" not in docstring
