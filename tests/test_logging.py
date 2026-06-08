import json

from bank_reconciliation_agent.core.logging import bind_trace_context, configure_logging, log


def test_logging_outputs_json_with_bound_trace_context(capsys) -> None:
    configure_logging()
    bind_trace_context(trace_id="trace-001", user_id="user-001", thread_id="thread-001")

    log.info("llm_call", agent_name="AuditAgent", step="decision", prompt_version="v1")

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["event"] == "llm_call"
    assert payload["trace_id"] == "trace-001"
    assert payload["user_id"] == "user-001"
    assert payload["thread_id"] == "thread-001"
    assert payload["agent_name"] == "AuditAgent"
    assert payload["step"] == "decision"
    assert payload["prompt_version"] == "v1"
