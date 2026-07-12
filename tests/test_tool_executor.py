from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Event

import pytest
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import OperationalError

from bank_reconciliation_agent.schemas.tools import (
    ConfirmedCase,
    ConfirmedCasesOutput,
    LoadConfirmedCasesArgs,
    LookupT1ContextArgs,
    SearchRulesArgs,
    SearchRulesOutput,
    T1ContextOutput,
    ToolAttemptRecord,
    ToolCallResult,
    ToolContext,
)
from bank_reconciliation_agent.schemas.rag import RagSearchItem
from bank_reconciliation_agent.services.tool_executor import (
    SHARED_EXECUTOR_MAX_WORKERS,
    TOOL_POLICIES,
    CircuitOpenError,
    ToolDefinition,
    ToolExecutor,
    ToolPolicy,
    ToolTransientError,
    get_shared_executor,
    safe_tool_projection,
)


SECRET_QUERY = "why is flow SENSITIVE_QUERY_TEXT unmatched"
SECRET_RULE_BODY = "TOP_SECRET_RULE_CONTENT should never leak"
SECRET_OPINION = "PRIVATE_AUDIT_OPINION should never leak"


def _ctx(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "user_id": "demo_user",
        "task_id": "T1",
        "flow_id": "F1",
        "scenario_type": "BANK_CLEARING",
        "exception_branch": "BC-R003",
        "fallback_level": 0,
    }
    base.update(over)
    return base


def _rag_item(chunk_id: str, content: str = SECRET_RULE_BODY) -> RagSearchItem:
    return RagSearchItem(
        chunk_id=chunk_id,
        source="rule",
        source_name="clearing_rules",
        source_url="local://rules",
        source_file="rules.yaml",
        section_title="BC-R003",
        element_type="rule",
        business_tags=["clearing"],
        score=0.91,
        content=content,
    )


def _make_executor(
    adapter,
    *,
    name: str = "search_rules",
    input_schema=SearchRulesArgs,
    output_schema=SearchRulesOutput,
    policy: ToolPolicy | None = None,
    authorized: bool = True,
    scenario_ok: bool = True,
    executor=None,
    sleeper=None,
    calls: list | None = None,
) -> ToolExecutor:
    definition = ToolDefinition(
        name=name,
        input_schema=input_schema,
        output_schema=output_schema,
        adapter=adapter,
        scenario_predicate=lambda ctx: scenario_ok,
        policy=policy or ToolPolicy(timeout_s=5.0, max_attempts=2, backoff_s=0.0),
    )
    authorizer = lambda ctx: authorized  # noqa: E731
    return ToolExecutor(
        {name: definition},
        authorizer,
        executor=executor,
        sleeper=sleeper or (lambda seconds: None),
    )


# --------------------------------------------------------------------------- #
# Schema contract
# --------------------------------------------------------------------------- #


def test_tool_context_rejects_extra_and_blank_identity() -> None:
    ToolContext(**_ctx())

    with pytest.raises(ValidationError):
        ToolContext(**_ctx(), role="admin")

    with pytest.raises(ValidationError):
        ToolContext(**_ctx(user_id="   "))

    with pytest.raises(ValidationError):
        ToolContext(**_ctx(scenario_type="OTHER"))


def test_args_models_reject_identity_override() -> None:
    SearchRulesArgs(query="hello")
    LoadConfirmedCasesArgs()
    LookupT1ContextArgs()

    with pytest.raises(ValidationError):
        SearchRulesArgs(query="hello", user_id="attacker")

    with pytest.raises(ValidationError):
        LoadConfirmedCasesArgs(task_id="other")

    with pytest.raises(ValidationError):
        LookupT1ContextArgs(flow_id="other")


def test_success_is_derived_from_status_and_not_settable() -> None:
    succeeded = ToolCallResult(
        tool_name="search_rules",
        status="SUCCEEDED",
        result=SearchRulesOutput(items=[_rag_item("c1")]),
        attempt=1,
        duration_ms=1.0,
        attempts=[ToolAttemptRecord(attempt=1, status="SUCCEEDED", duration_ms=1.0)],
    )
    assert succeeded.success is True

    empty = ToolCallResult(
        tool_name="search_rules",
        status="EMPTY",
        attempt=1,
        duration_ms=1.0,
        attempts=[ToolAttemptRecord(attempt=1, status="EMPTY", duration_ms=1.0)],
    )
    assert empty.success is True

    failed = ToolCallResult(
        tool_name="search_rules",
        status="FAILED",
        error_type="TIMEOUT",
        fallback_reason="TOOL_TIMEOUT",
        retryable=True,
        attempt=2,
        duration_ms=1.0,
        attempts=[ToolAttemptRecord(attempt=2, status="FAILED", duration_ms=1.0, error_type="TIMEOUT", retryable=True)],
    )
    assert failed.success is False

    with pytest.raises(ValidationError):
        ToolCallResult(
            tool_name="search_rules",
            status="FAILED",
            success=True,
            error_type="TIMEOUT",
            fallback_reason="TOOL_TIMEOUT",
            attempt=1,
            duration_ms=1.0,
            attempts=[ToolAttemptRecord(attempt=1, status="FAILED", duration_ms=1.0, error_type="TIMEOUT", retryable=True)],
        )


def test_result_field_combinations_enforced() -> None:
    with pytest.raises(ValidationError):  # EMPTY must not carry error_type
        ToolCallResult(
            tool_name="search_rules",
            status="EMPTY",
            error_type="TIMEOUT",
            attempt=1,
            duration_ms=1.0,
            attempts=[ToolAttemptRecord(attempt=1, status="EMPTY", duration_ms=1.0)],
        )

    with pytest.raises(ValidationError):  # FAILED must carry error_type + fallback_reason
        ToolCallResult(
            tool_name="search_rules",
            status="FAILED",
            attempt=1,
            duration_ms=1.0,
            attempts=[ToolAttemptRecord(attempt=1, status="FAILED", duration_ms=1.0, error_type="TIMEOUT", retryable=True)],
        )

    with pytest.raises(ValidationError):  # FAILED must not carry result
        ToolCallResult(
            tool_name="search_rules",
            status="FAILED",
            result=SearchRulesOutput(items=[]),
            error_type="INTERNAL_ERROR",
            fallback_reason="TOOL_INTERNAL_ERROR",
            attempt=1,
            duration_ms=1.0,
            attempts=[ToolAttemptRecord(attempt=1, status="FAILED", duration_ms=1.0, error_type="INTERNAL_ERROR")],
        )

    with pytest.raises(ValidationError):  # SUCCEEDED must carry result
        ToolCallResult(
            tool_name="search_rules",
            status="SUCCEEDED",
            attempt=1,
            duration_ms=1.0,
            attempts=[ToolAttemptRecord(attempt=1, status="SUCCEEDED", duration_ms=1.0)],
        )


def test_attempt_record_number_is_one_or_two() -> None:
    ToolAttemptRecord(attempt=1, status="SUCCEEDED", duration_ms=0.0)
    ToolAttemptRecord(attempt=2, status="SUCCEEDED", duration_ms=0.0)

    with pytest.raises(ValidationError):
        ToolAttemptRecord(attempt=3, status="SUCCEEDED", duration_ms=0.0)

    with pytest.raises(ValidationError):
        ToolAttemptRecord(attempt=1, status="FAILED", duration_ms=-1.0, error_type="TIMEOUT")


# --------------------------------------------------------------------------- #
# Registry and pre-adapter fail closed
# --------------------------------------------------------------------------- #


def test_unknown_tool_fails_closed_without_adapter() -> None:
    calls: list[int] = []

    def adapter(args, ctx):
        calls.append(1)
        return SearchRulesOutput(items=[])

    executor = _make_executor(adapter)
    result = executor.execute("no_such_tool", SearchRulesArgs(query="x"), _ctx())

    assert result.status == "FAILED"
    assert result.error_type == "UNKNOWN_TOOL"
    assert result.fallback_reason == "TOOL_UNKNOWN"
    assert result.success is False
    assert calls == []


def test_invalid_context_fails_closed_without_adapter() -> None:
    calls: list[int] = []

    def adapter(args, ctx):
        calls.append(1)
        return SearchRulesOutput(items=[])

    executor = _make_executor(adapter)
    result = executor.execute("search_rules", SearchRulesArgs(query="x"), _ctx(user_id="  "))

    assert result.status == "FAILED"
    assert result.error_type == "VALIDATION_ERROR"
    assert calls == []


def test_input_args_cannot_carry_identity_fields() -> None:
    calls: list[int] = []

    def adapter(args, ctx):
        calls.append(1)
        return SearchRulesOutput(items=[])

    executor = _make_executor(adapter)
    result = executor.execute("search_rules", {"query": "x", "user_id": "attacker"}, _ctx())

    assert result.status == "FAILED"
    assert result.error_type == "VALIDATION_ERROR"
    assert calls == []


def test_authorization_denied_fails_closed_without_adapter() -> None:
    calls: list[int] = []

    def adapter(args, ctx):
        calls.append(1)
        return SearchRulesOutput(items=[])

    executor = _make_executor(adapter, authorized=False)
    result = executor.execute("search_rules", SearchRulesArgs(query="x"), _ctx())

    assert result.status == "FAILED"
    assert result.error_type == "PERMISSION_DENIED"
    assert result.fallback_reason == "TOOL_ACCESS_DENIED"
    assert calls == []


def test_scenario_denied_fails_closed_without_adapter() -> None:
    calls: list[int] = []

    def adapter(args, ctx):
        calls.append(1)
        return SearchRulesOutput(items=[])

    executor = _make_executor(adapter, scenario_ok=False)
    result = executor.execute("search_rules", SearchRulesArgs(query="x"), _ctx())

    assert result.status == "FAILED"
    assert result.error_type == "PERMISSION_DENIED"
    assert calls == []


def test_output_schema_drift_is_internal_error_not_validation_error() -> None:
    def adapter(args, ctx):
        return {"unexpected": "shape"}

    executor = _make_executor(adapter)
    result = executor.execute("search_rules", SearchRulesArgs(query="x"), _ctx())

    assert result.status == "FAILED"
    assert result.error_type == "INTERNAL_ERROR"
    assert result.fallback_reason == "TOOL_INTERNAL_ERROR"
    assert len(result.attempts) == 1


# --------------------------------------------------------------------------- #
# Outcomes, attempts, retry, timeout
# --------------------------------------------------------------------------- #


def test_succeeded_single_attempt() -> None:
    def adapter(args, ctx):
        return SearchRulesOutput(items=[_rag_item("c1")])

    executor = _make_executor(adapter)
    result = executor.execute("search_rules", SearchRulesArgs(query=SECRET_QUERY), _ctx())

    assert result.status == "SUCCEEDED"
    assert result.attempt == 1
    assert result.retry_recovered is False
    assert len(result.attempts) == 1
    assert result.duration_ms >= 0.0


def test_empty_output_is_empty_and_not_retried() -> None:
    calls: list[int] = []

    def adapter(args, ctx):
        calls.append(1)
        return SearchRulesOutput(items=[])

    executor = _make_executor(adapter)
    result = executor.execute("search_rules", SearchRulesArgs(query="x"), _ctx())

    assert result.status == "EMPTY"
    assert result.error_type is None
    assert result.retryable is False
    assert result.result is None
    assert len(result.attempts) == 1
    assert calls == [1]


def test_adapter_returning_none_maps_to_empty() -> None:
    def adapter(args, ctx):
        return None

    executor = _make_executor(
        adapter,
        name="lookup_t1_context",
        input_schema=LookupT1ContextArgs,
        output_schema=T1ContextOutput,
    )
    result = executor.execute("lookup_t1_context", LookupT1ContextArgs(), _ctx())

    assert result.status == "EMPTY"
    assert result.result is None


def test_transient_error_recovers_on_second_attempt() -> None:
    calls: list[int] = []

    def adapter(args, ctx):
        calls.append(1)
        if len(calls) == 1:
            raise ToolTransientError("temporary")
        return SearchRulesOutput(items=[_rag_item("c1")])

    executor = _make_executor(adapter)
    result = executor.execute("search_rules", SearchRulesArgs(query="x"), _ctx())

    assert result.status == "SUCCEEDED"
    assert result.attempt == 2
    assert result.retry_recovered is True
    assert result.error_type is None
    assert result.retryable is False
    assert len(result.attempts) == 2
    assert result.attempts[0].status == "FAILED"
    assert result.attempts[0].error_type == "TRANSIENT_READ_ERROR"
    assert result.attempts[0].retryable is True
    assert result.attempts[1].status == "SUCCEEDED"


def test_transient_error_exhausted_after_two_attempts() -> None:
    calls: list[int] = []

    def adapter(args, ctx):
        calls.append(1)
        raise ToolTransientError("still failing")

    executor = _make_executor(adapter)
    result = executor.execute("search_rules", SearchRulesArgs(query="x"), _ctx())

    assert result.status == "FAILED"
    assert result.error_type == "TRANSIENT_READ_ERROR"
    assert result.fallback_reason == "TOOL_TRANSIENT_READ_ERROR"
    assert result.retryable is True
    assert result.attempt == 2
    assert len(result.attempts) == 2
    assert calls == [1, 1]


def test_non_retryable_internal_error_has_single_attempt() -> None:
    calls: list[int] = []

    def adapter(args, ctx):
        calls.append(1)
        raise RuntimeError("boom")

    executor = _make_executor(adapter)
    result = executor.execute("search_rules", SearchRulesArgs(query="x"), _ctx())

    assert result.status == "FAILED"
    assert result.error_type == "INTERNAL_ERROR"
    assert result.retryable is False
    assert len(result.attempts) == 1
    assert calls == [1]


def test_circuit_open_is_failed_not_empty_and_not_retried() -> None:
    calls: list[int] = []

    def adapter(args, ctx):
        calls.append(1)
        raise CircuitOpenError("rag breaker open")

    executor = _make_executor(adapter)
    result = executor.execute("search_rules", SearchRulesArgs(query="x"), _ctx())

    assert result.status == "FAILED"
    assert result.error_type == "CIRCUIT_OPEN"
    assert result.fallback_reason == "RAG_CIRCUIT_OPEN"
    assert result.retryable is False
    assert len(result.attempts) == 1
    assert calls == [1]


def test_infra_error_reraised_after_local_retry_exhausted() -> None:
    calls: list[int] = []

    def adapter(args, ctx):
        calls.append(1)
        raise OperationalError("SELECT 1", {}, Exception("db down"))

    executor = _make_executor(adapter)
    with pytest.raises(OperationalError):
        executor.execute("search_rules", SearchRulesArgs(query="x"), _ctx())

    assert calls == [1, 1]


def test_infra_error_attempts_emit_safe_structured_observations() -> None:
    from structlog.testing import capture_logs

    def adapter(args, ctx):
        raise OperationalError("SELECT secret_table", {}, Exception("dsn=postgres://db"))

    executor = _make_executor(adapter)
    with capture_logs() as logs:
        with pytest.raises(OperationalError):
            executor.execute("search_rules", SearchRulesArgs(query=SECRET_QUERY), _ctx())

    attempts = [row for row in logs if row.get("event") == "tool_attempt"]
    assert len(attempts) == 2
    assert [row["attempt"] for row in attempts] == [1, 2]
    for row in attempts:
        assert row["tool_name"] == "search_rules"
        assert row["status"] == "FAILED"
        assert row["error_type"] == "TRANSIENT_READ_ERROR"
        assert row["retryable"] is True
        assert isinstance(row["duration_ms"], float)
        assert set(row) <= {
            "event",
            "log_level",
            "tool_name",
            "attempt",
            "status",
            "duration_ms",
            "error_type",
            "retryable",
        }
        _assert_no_sensitive(row)


def test_redis_infra_error_recovers_and_records_transient() -> None:
    calls: list[int] = []

    def adapter(args, ctx):
        calls.append(1)
        if len(calls) == 1:
            raise RedisConnectionError("redis unavailable")
        return SearchRulesOutput(items=[_rag_item("c1")])

    executor = _make_executor(adapter)
    result = executor.execute("search_rules", SearchRulesArgs(query="x"), _ctx())

    assert result.status == "SUCCEEDED"
    assert result.retry_recovered is True
    assert result.attempts[0].error_type == "TRANSIENT_READ_ERROR"
    assert len(result.attempts) == 2


def test_timeout_exhausts_after_two_attempts() -> None:
    finish = Event()

    def adapter(args, ctx):
        finish.wait(timeout=2.0)
        return SearchRulesOutput(items=[_rag_item("c1")])

    pool = ThreadPoolExecutor(max_workers=4)
    try:
        executor = _make_executor(
            adapter,
            policy=ToolPolicy(timeout_s=0.02, max_attempts=2, backoff_s=0.0),
            executor=pool,
        )
        result = executor.execute("search_rules", SearchRulesArgs(query="x"), _ctx())
    finally:
        finish.set()
        pool.shutdown(wait=True)

    assert result.status == "FAILED"
    assert result.error_type == "TIMEOUT"
    assert result.fallback_reason == "TOOL_TIMEOUT"
    assert result.retryable is True
    assert result.attempt == 2
    assert len(result.attempts) == 2


def test_timeout_late_completion_does_not_overwrite_returned_result() -> None:
    release = Event()

    def adapter(args, ctx):
        release.wait(timeout=2.0)
        return SearchRulesOutput(items=[_rag_item("late")])

    pool = ThreadPoolExecutor(max_workers=4)
    try:
        executor = _make_executor(
            adapter,
            policy=ToolPolicy(timeout_s=0.02, max_attempts=2, backoff_s=0.0),
            executor=pool,
        )
        result = executor.execute("search_rules", SearchRulesArgs(query="x"), _ctx())
        assert result.status == "FAILED"
        assert result.error_type == "TIMEOUT"
        release.set()
    finally:
        release.set()
        pool.shutdown(wait=True)

    assert result.status == "FAILED"
    assert result.result is None


def test_shared_pool_capacity_is_four() -> None:
    assert SHARED_EXECUTOR_MAX_WORKERS == 4
    assert get_shared_executor()._max_workers == 4


def test_tool_policy_single_source_matches_spec() -> None:
    assert set(TOOL_POLICIES) == {"search_rules", "load_confirmed_cases", "lookup_t1_context"}
    assert TOOL_POLICIES["search_rules"] == ToolPolicy(timeout_s=30.0, max_attempts=2, backoff_s=0.05)
    assert TOOL_POLICIES["load_confirmed_cases"] == ToolPolicy(timeout_s=5.0, max_attempts=2, backoff_s=0.05)
    assert TOOL_POLICIES["lookup_t1_context"] == ToolPolicy(timeout_s=5.0, max_attempts=2, backoff_s=0.05)


# --------------------------------------------------------------------------- #
# Safe projection
# --------------------------------------------------------------------------- #

_FORBIDDEN_KEYS = {
    "args",
    "query",
    "content",
    "result",
    "exception",
    "traceback",
    "sql",
    "dsn",
    "token",
}
_FORBIDDEN_VALUES = {SECRET_QUERY, SECRET_RULE_BODY, SECRET_OPINION}


def _assert_no_sensitive(node: object) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            assert key not in _FORBIDDEN_KEYS, f"forbidden key leaked: {key}"
            _assert_no_sensitive(value)
    elif isinstance(node, (list, tuple, set)):
        for item in node:
            _assert_no_sensitive(item)
    elif isinstance(node, str):
        for secret in _FORBIDDEN_VALUES:
            assert secret not in node, f"sensitive value leaked: {node!r}"


def test_safe_projection_search_rules_only_exposes_allowlist() -> None:
    def adapter(args, ctx):
        return SearchRulesOutput(items=[_rag_item("chunk-42", content=SECRET_RULE_BODY)])

    executor = _make_executor(adapter)
    result = executor.execute("search_rules", SearchRulesArgs(query=SECRET_QUERY), _ctx())

    projection = safe_tool_projection(result)

    assert projection["tool_name"] == "search_rules"
    assert projection["status"] == "SUCCEEDED"
    assert projection["result_count"] == 1
    assert projection["evidence_ids"] == ["chunk-42"]
    _assert_no_sensitive(projection)


def test_safe_projection_confirmed_cases_exposes_flow_ids_only() -> None:
    def adapter(args, ctx):
        return ConfirmedCasesOutput(
            items=[
                ConfirmedCase(
                    flow_id="FC-1",
                    error_type="AMOUNT_MISMATCH",
                    exception_branch="BC-R003",
                    ai_audit_opinion=SECRET_OPINION,
                    ai_confidence=Decimal("0.90"),
                    handle_status="FIXED",
                )
            ]
        )

    executor = _make_executor(
        adapter,
        name="load_confirmed_cases",
        input_schema=LoadConfirmedCasesArgs,
        output_schema=ConfirmedCasesOutput,
    )
    result = executor.execute("load_confirmed_cases", LoadConfirmedCasesArgs(), _ctx(fallback_level=2))

    projection = safe_tool_projection(result)

    assert projection["evidence_ids"] == ["FC-1"]
    assert projection["result_count"] == 1
    _assert_no_sensitive(projection)


def test_safe_projection_t1_context_exposes_flow_id() -> None:
    def adapter(args, ctx):
        return T1ContextOutput(flow_id="BANK-9", accounting_date=date(2026, 7, 12))

    executor = _make_executor(
        adapter,
        name="lookup_t1_context",
        input_schema=LookupT1ContextArgs,
        output_schema=T1ContextOutput,
    )
    result = executor.execute("lookup_t1_context", LookupT1ContextArgs(), _ctx())

    projection = safe_tool_projection(result)

    assert projection["evidence_ids"] == ["BANK-9"]
    assert projection["result_count"] == 1
    _assert_no_sensitive(projection)


def test_safe_projection_failed_call_has_no_evidence() -> None:
    def adapter(args, ctx):
        raise CircuitOpenError("open")

    executor = _make_executor(adapter)
    result = executor.execute("search_rules", SearchRulesArgs(query=SECRET_QUERY), _ctx())

    projection = safe_tool_projection(result)

    assert projection["status"] == "FAILED"
    assert projection["error_type"] == "CIRCUIT_OPEN"
    assert projection["result_count"] == 0
    assert projection["evidence_ids"] == []
    _assert_no_sensitive(projection)
