from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import OperationalError

from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchRequest, RagSearchResponse
from bank_reconciliation_agent.schemas.tools import (
    ConfirmedCasesOutput,
    LoadConfirmedCasesArgs,
    LookupT1ContextArgs,
    SearchRulesArgs,
    SearchRulesOutput,
    T1ContextOutput,
)
from bank_reconciliation_agent.services.circuit_breaker import CircuitBreaker
from bank_reconciliation_agent.services.exception_router import ExceptionRouter, find_t1_candidate
from bank_reconciliation_agent.services.fallback import LedgerFallbackCaseProvider
from bank_reconciliation_agent.services.ledger import LedgerService
from bank_reconciliation_agent.services.task import TaskService
from bank_reconciliation_agent.services.tool_adapters import (
    build_default_registry,
    make_search_rules_adapter,
    make_tenant_authorizer,
)
from bank_reconciliation_agent.services.tool_executor import (
    CircuitOpenError,
    ToolExecutor,
)
from bank_reconciliation_agent.services.transactions import TransactionService
from bank_reconciliation_agent.schemas.ledger import LedgerRow


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #


def _bank_row(
    flow_id: str,
    amount: str,
    *,
    accounting_date: object,
    reference_no: str | None = None,
    merchant_order_no: str | None = None,
    voucher_no: str | None = None,
) -> dict[str, object]:
    return {
        "flow_id": flow_id,
        "amount": Decimal(amount),
        "debit_amount": Decimal("0.00"),
        "credit_amount": Decimal(amount),
        "trade_time": datetime(2026, 6, 11, 10, 0, 0),
        "accounting_date": accounting_date,
        "summary": "核心流水",
        "reference_no": reference_no,
        "merchant_order_no": merchant_order_no,
        "voucher_no": voucher_no,
    }


def _clear_row(
    flow_id: str,
    amount: str,
    *,
    trade_date: object = "2026-06-10",
    reference_no: str | None = None,
    merchant_order_no: str | None = None,
    voucher_no: str | None = None,
) -> dict[str, object]:
    return {
        "flow_id": flow_id,
        "amount": Decimal(amount),
        "transaction_amount": Decimal(amount),
        "net_amount": Decimal(amount),
        "trade_time": "23:30",
        "trade_date": trade_date,
        "summary": "清算流水",
        "payer_name_masked": f"付款方-{flow_id}",
        "payee_name_masked": f"收款方-{flow_id}",
        "reference_no": reference_no,
        "merchant_order_no": merchant_order_no,
        "voucher_no": voucher_no,
    }


def _seed_task(
    task_service: TaskService,
    *,
    user_id: str,
    task_id: str,
    scenario_type: str,
) -> None:
    task_service.replace_task(
        user_id=user_id,
        task_id=task_id,
        scenario_type=scenario_type,
        total_bank_rows=1,
        total_clear_rows=1,
        auto_fixed_rows=0,
        pending_ai_rows=0,
        pending_human_rows=1,
    )


def _ctx(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "user_id": "demo_user",
        "task_id": "T_T1",
        "flow_id": "CLEAR_CUTOFF",
        "scenario_type": "BANK_CLEARING",
        "exception_branch": "BC-R003",
        "fallback_level": 0,
    }
    base.update(over)
    return base


class _StubRetriever:
    def __init__(self, response: RagSearchResponse | Exception) -> None:
        self._response = response
        self.calls = 0

    def search(self, request: RagSearchRequest) -> RagSearchResponse:
        self.calls += 1
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _rag_item(chunk_id: str) -> RagSearchItem:
    return RagSearchItem(
        chunk_id=chunk_id,
        source="rule",
        source_name="clearing_rules",
        source_url="local://rules",
        source_file="data/rag/raw_sources/bank_clearing/x.md",
        section_title="BC-R003",
        element_type="rule",
        business_tags=["clearing"],
        score=0.9,
        content="rule body",
    )


def _executor(registry, authorizer) -> ToolExecutor:
    return ToolExecutor(registry, authorizer, sleeper=lambda s: None)


# --------------------------------------------------------------------------- #
# find_t1_candidate pure function
# --------------------------------------------------------------------------- #


def test_find_t1_candidate_is_public_and_matches_on_amount_date_reference() -> None:
    clear_row = _clear_row("CLEAR_CUTOFF", "100.00", reference_no="REF-100")
    bank_rows = [_bank_row("CORE_T1", "100.00", accounting_date=date(2026, 6, 11), reference_no="REF-100")]

    assert find_t1_candidate(clear_row, bank_rows) == {
        "flow_id": "CORE_T1",
        "accounting_date": "2026-06-11",
    }


def test_find_t1_candidate_returns_none_without_reference_intersection() -> None:
    clear_row = _clear_row("CLEAR_CUTOFF", "100.00", reference_no="REF-100")
    bank_rows = [_bank_row("CORE_X", "100.00", accounting_date=date(2026, 6, 11), reference_no="REF-OTHER")]

    assert find_t1_candidate(clear_row, bank_rows) is None


def test_router_classify_still_attaches_t1_candidate_via_shared_function() -> None:
    bank_df = pd.DataFrame(
        [_bank_row("CORE_T1", "100.00", accounting_date=date(2026, 6, 11), reference_no="REF-100")]
    )
    clear_df = pd.DataFrame([_clear_row("CLEAR_CUTOFF", "100.00", reference_no="REF-100")])

    results = {
        r.flow_id: r
        for r in ExceptionRouter().classify(bank_df, clear_df, scenario_type="BANK_CLEARING")
    }

    assert results["CLEAR_CUTOFF"].exception_branch == "BC-R003"
    assert results["CLEAR_CUTOFF"].t1_candidate == {
        "flow_id": "CORE_T1",
        "accounting_date": "2026-06-11",
    }


# --------------------------------------------------------------------------- #
# search_rules adapter + breaker
# --------------------------------------------------------------------------- #


def test_search_rules_succeeded_with_real_items() -> None:
    retriever = _StubRetriever(RagSearchResponse(items=[_rag_item("c1")], rewritten_query=None))
    breaker = CircuitBreaker(fail_threshold=2, open_seconds=30, time_fn=lambda: 0.0)
    registry = build_default_registry(
        retriever=retriever,
        rag_breaker=breaker,
    )
    executor = _executor(registry, lambda ctx: True)

    result = executor.execute("search_rules", SearchRulesArgs(query="cutoff"), _ctx())

    assert result.status == "SUCCEEDED"
    assert isinstance(result.result, SearchRulesOutput)
    assert [i.chunk_id for i in result.result.items] == ["c1"]
    assert retriever.calls == 1


def test_search_rules_empty_is_empty_not_failed() -> None:
    retriever = _StubRetriever(RagSearchResponse(items=[], rewritten_query=None))
    breaker = CircuitBreaker(fail_threshold=2, open_seconds=30, time_fn=lambda: 0.0)
    registry = build_default_registry(
        retriever=retriever,
        rag_breaker=breaker,
    )
    executor = _executor(registry, lambda ctx: True)

    result = executor.execute("search_rules", SearchRulesArgs(query="nothing"), _ctx())

    assert result.status == "EMPTY"
    assert result.error_type is None
    assert breaker.state == "CLOSED"


def test_search_rules_breaker_open_is_circuit_open_and_skips_retriever() -> None:
    retriever = _StubRetriever(RagSearchResponse(items=[_rag_item("c1")], rewritten_query=None))
    breaker = CircuitBreaker(fail_threshold=1, open_seconds=30, time_fn=lambda: 0.0)
    breaker.record_failure()  # OPEN
    assert breaker.state == "OPEN"
    registry = build_default_registry(
        retriever=retriever,
        rag_breaker=breaker,
    )
    executor = _executor(registry, lambda ctx: True)

    result = executor.execute("search_rules", SearchRulesArgs(query="cutoff"), _ctx())

    assert result.status == "FAILED"
    assert result.error_type == "CIRCUIT_OPEN"
    assert result.fallback_reason == "RAG_CIRCUIT_OPEN"
    assert retriever.calls == 0


def test_search_rules_retriever_exception_records_failure_and_reraises_as_internal() -> None:
    retriever = _StubRetriever(RuntimeError("chroma down"))
    breaker = CircuitBreaker(fail_threshold=2, open_seconds=30, time_fn=lambda: 0.0)
    registry = build_default_registry(
        retriever=retriever,
        rag_breaker=breaker,
    )
    executor = _executor(registry, lambda ctx: True)

    result = executor.execute("search_rules", SearchRulesArgs(query="cutoff"), _ctx())

    assert result.status == "FAILED"
    assert result.error_type == "INTERNAL_ERROR"
    assert breaker._failure_count == 1  # record_failure called once


def test_search_rules_half_open_success_recovers_closed() -> None:
    now = {"t": 0.0}
    breaker = CircuitBreaker(fail_threshold=1, open_seconds=10, time_fn=lambda: now["t"])
    breaker.record_failure()  # OPEN
    now["t"] = 11.0
    assert breaker.state == "HALF_OPEN"

    retriever = _StubRetriever(RagSearchResponse(items=[_rag_item("c1")], rewritten_query=None))
    registry = build_default_registry(
        retriever=retriever,
        rag_breaker=breaker,
    )
    executor = _executor(registry, lambda ctx: True)

    result = executor.execute("search_rules", SearchRulesArgs(query="cutoff"), _ctx())

    assert result.status == "SUCCEEDED"
    assert breaker.state == "CLOSED"


def test_search_rules_infra_error_reraised_after_local_retry() -> None:
    retriever = _StubRetriever(OperationalError("SELECT 1", {}, Exception("db down")))
    breaker = CircuitBreaker(fail_threshold=5, open_seconds=30, time_fn=lambda: 0.0)
    registry = build_default_registry(
        retriever=retriever,
        rag_breaker=breaker,
    )
    executor = _executor(registry, lambda ctx: True)

    with pytest.raises(OperationalError):
        executor.execute("search_rules", SearchRulesArgs(query="cutoff"), _ctx())

    assert retriever.calls == 2


def test_search_rules_operational_error_not_counted_by_breaker_at_threshold_one() -> None:
    retriever = _StubRetriever(OperationalError("SELECT 1", {}, Exception("db down")))
    breaker = CircuitBreaker(fail_threshold=1, open_seconds=30, time_fn=lambda: 0.0)
    registry = build_default_registry(
        retriever=retriever,
        rag_breaker=breaker,
    )
    executor = _executor(registry, lambda ctx: True)

    with pytest.raises(OperationalError):
        executor.execute("search_rules", SearchRulesArgs(query="cutoff"), _ctx())

    assert retriever.calls == 2
    assert breaker.state == "CLOSED"
    assert breaker._failure_count == 0


def test_search_rules_redis_error_not_counted_by_breaker_at_threshold_one() -> None:
    retriever = _StubRetriever(RedisConnectionError("redis gone"))
    breaker = CircuitBreaker(fail_threshold=1, open_seconds=30, time_fn=lambda: 0.0)
    registry = build_default_registry(
        retriever=retriever,
        rag_breaker=breaker,
    )
    executor = _executor(registry, lambda ctx: True)

    with pytest.raises(RedisConnectionError):
        executor.execute("search_rules", SearchRulesArgs(query="cutoff"), _ctx())

    assert retriever.calls == 2
    assert breaker.state == "CLOSED"
    assert breaker._failure_count == 0


def test_search_rules_ordinary_exception_still_counts_toward_breaker() -> None:
    retriever = _StubRetriever(RuntimeError("chroma down"))
    breaker = CircuitBreaker(fail_threshold=2, open_seconds=30, time_fn=lambda: 0.0)
    registry = build_default_registry(
        retriever=retriever,
        rag_breaker=breaker,
    )
    executor = _executor(registry, lambda ctx: True)

    result = executor.execute("search_rules", SearchRulesArgs(query="cutoff"), _ctx())

    assert result.status == "FAILED"
    assert result.error_type == "INTERNAL_ERROR"
    assert breaker._failure_count == 1


# --------------------------------------------------------------------------- #
# load_confirmed_cases adapter + scenario allowlist
# --------------------------------------------------------------------------- #


def _seed_confirmed_case(
    ledger_service: LedgerService,
    *,
    user_id: str,
    task_id: str,
    exception_branch: str,
) -> None:
    ledger_service.replace_task_rows(
        user_id=user_id,
        task_id=task_id,
        scenario_type="BANK_CLEARING",
        rows=[
            LedgerRow(
                id=0,
                task_id=task_id,
                flow_id="FC_1",
                error_type="CUTOFF_CROSS_DAY",
                exception_branch=exception_branch,
                bank_amount=Decimal("100.00"),
                clear_amount=Decimal("100.00"),
                discrepancy_amount=Decimal("0.00"),
                ai_audit_opinion="历史确认意见",
                ai_confidence=Decimal("0.9000"),
                rag_source=None,
                handle_status="FIXED",
            )
        ],
    )


def test_load_confirmed_cases_requires_fallback_level_2() -> None:
    registry = build_default_registry()
    executor = _executor(registry, lambda ctx: True)

    result = executor.execute(
        "load_confirmed_cases",
        LoadConfirmedCasesArgs(),
        _ctx(fallback_level=0),
    )

    assert result.status == "FAILED"
    assert result.error_type == "PERMISSION_DENIED"


def test_load_confirmed_cases_empty_when_no_history() -> None:
    registry = build_default_registry()
    executor = _executor(registry, lambda ctx: True)

    result = executor.execute(
        "load_confirmed_cases",
        LoadConfirmedCasesArgs(),
        _ctx(fallback_level=2, exception_branch="BC-R999"),
    )

    assert result.status == "EMPTY"
    assert result.error_type is None


def test_load_confirmed_cases_succeeded_with_history() -> None:
    ledger_service = LedgerService()
    _seed_confirmed_case(
        ledger_service,
        user_id="demo_user",
        task_id="T_CASES",
        exception_branch="BC-R003",
    )
    registry = build_default_registry(
        ledger_service=LedgerFallbackCaseProvider(),
    )
    executor = _executor(registry, lambda ctx: True)

    result = executor.execute(
        "load_confirmed_cases",
        LoadConfirmedCasesArgs(),
        _ctx(task_id="T_CASES", fallback_level=2, exception_branch="BC-R003"),
    )

    assert result.status == "SUCCEEDED"
    assert isinstance(result.result, ConfirmedCasesOutput)
    assert result.result.items[0].flow_id == "FC_1"


# --------------------------------------------------------------------------- #
# lookup_t1_context adapter + tenant isolation
# --------------------------------------------------------------------------- #


def _seed_clearing_transactions(
    transaction_service: TransactionService,
    *,
    user_id: str,
    task_id: str,
) -> None:
    bank_df = pd.DataFrame(
        [_bank_row("CORE_T1", "100.00", accounting_date=date(2026, 6, 11), reference_no="REF-100")]
    )
    clear_df = pd.DataFrame([_clear_row("CLEAR_CUTOFF", "100.00", reference_no="REF-100")])
    transaction_service.replace_task_rows(
        user_id=user_id,
        task_id=task_id,
        bank_df=bank_df,
        clear_df=clear_df,
    )


def test_lookup_t1_context_only_bank_clearing_bc_r003() -> None:
    registry = build_default_registry()
    executor = _executor(registry, lambda ctx: True)

    result = executor.execute(
        "lookup_t1_context",
        LookupT1ContextArgs(),
        _ctx(exception_branch="BC-R001"),
    )

    assert result.status == "FAILED"
    assert result.error_type == "PERMISSION_DENIED"


def test_lookup_t1_context_succeeded_from_persisted_rows() -> None:
    transaction_service = TransactionService()
    _seed_clearing_transactions(transaction_service, user_id="demo_user", task_id="T_T1S")
    registry = build_default_registry(
        transaction_service=transaction_service,
    )
    executor = _executor(registry, lambda ctx: True)

    result = executor.execute(
        "lookup_t1_context",
        LookupT1ContextArgs(),
        _ctx(task_id="T_T1S", flow_id="CLEAR_CUTOFF"),
    )

    assert result.status == "SUCCEEDED"
    assert isinstance(result.result, T1ContextOutput)
    assert result.result.flow_id == "CORE_T1"
    assert result.result.accounting_date == date(2026, 6, 11)


def test_lookup_t1_context_empty_when_no_match() -> None:
    transaction_service = TransactionService()
    bank_df = pd.DataFrame(
        [_bank_row("CORE_X", "100.00", accounting_date=date(2026, 6, 11), reference_no="REF-OTHER")]
    )
    clear_df = pd.DataFrame([_clear_row("CLEAR_NOMATCH", "100.00", reference_no="REF-100")])
    transaction_service.replace_task_rows(
        user_id="demo_user", task_id="T_T1E", bank_df=bank_df, clear_df=clear_df
    )
    registry = build_default_registry(
        transaction_service=transaction_service,
    )
    executor = _executor(registry, lambda ctx: True)

    result = executor.execute(
        "lookup_t1_context",
        LookupT1ContextArgs(),
        _ctx(task_id="T_T1E", flow_id="CLEAR_NOMATCH"),
    )

    assert result.status == "EMPTY"


def test_lookup_t1_context_does_not_read_other_task_rows() -> None:
    transaction_service = TransactionService()
    # task A has the matching bank row
    _seed_clearing_transactions(transaction_service, user_id="demo_user", task_id="T_A")
    # task B has only the clear row, no matching bank row
    clear_df = pd.DataFrame([_clear_row("CLEAR_CUTOFF", "100.00", reference_no="REF-100")])
    transaction_service.replace_task_rows(
        user_id="demo_user", task_id="T_B", bank_df=pd.DataFrame([]), clear_df=clear_df
    )
    registry = build_default_registry(
        transaction_service=transaction_service,
    )
    executor = _executor(registry, lambda ctx: True)

    result = executor.execute(
        "lookup_t1_context",
        LookupT1ContextArgs(),
        _ctx(task_id="T_B", flow_id="CLEAR_CUTOFF"),
    )

    assert result.status == "EMPTY"


def test_upload_classification_and_persisted_query_return_same_candidate() -> None:
    transaction_service = TransactionService()
    bank_df = pd.DataFrame(
        [_bank_row("CORE_T1", "100.00", accounting_date=date(2026, 6, 11), reference_no="REF-100")]
    )
    clear_df = pd.DataFrame([_clear_row("CLEAR_CUTOFF", "100.00", reference_no="REF-100")])

    upload = {
        r.flow_id: r
        for r in ExceptionRouter().classify(bank_df, clear_df, scenario_type="BANK_CLEARING")
    }["CLEAR_CUTOFF"].t1_candidate

    transaction_service.replace_task_rows(
        user_id="demo_user", task_id="T_SAME", bank_df=bank_df, clear_df=clear_df
    )
    registry = build_default_registry(
        transaction_service=transaction_service,
    )
    executor = _executor(registry, lambda ctx: True)
    result = executor.execute(
        "lookup_t1_context",
        LookupT1ContextArgs(),
        _ctx(task_id="T_SAME", flow_id="CLEAR_CUTOFF"),
    )

    assert upload == {"flow_id": "CORE_T1", "accounting_date": "2026-06-11"}
    assert result.status == "SUCCEEDED"
    assert result.result.flow_id == upload["flow_id"]
    assert result.result.accounting_date.isoformat() == upload["accounting_date"]


# --------------------------------------------------------------------------- #
# Tenant authorizer (indistinguishable denials)
# --------------------------------------------------------------------------- #


def test_authorizer_rejects_missing_task_wrong_user_and_scenario_the_same_way() -> None:
    task_service = TaskService()
    transaction_service = TransactionService()
    _seed_task(task_service, user_id="owner", task_id="T_AUTH", scenario_type="BANK_CLEARING")
    _seed_clearing_transactions(transaction_service, user_id="owner", task_id="T_AUTH")

    authorizer = make_tenant_authorizer(
        task_service=task_service,
        transaction_service=transaction_service,
    )

    from bank_reconciliation_agent.schemas.tools import ToolContext

    ok = ToolContext(**_ctx(user_id="owner", task_id="T_AUTH", flow_id="CLEAR_CUTOFF"))
    missing_task = ToolContext(**_ctx(user_id="owner", task_id="NOPE", flow_id="CLEAR_CUTOFF"))
    wrong_user = ToolContext(**_ctx(user_id="intruder", task_id="T_AUTH", flow_id="CLEAR_CUTOFF"))
    wrong_flow = ToolContext(**_ctx(user_id="owner", task_id="T_AUTH", flow_id="GHOST"))
    wrong_scenario = ToolContext(
        **_ctx(user_id="owner", task_id="T_AUTH", flow_id="CLEAR_CUTOFF", scenario_type="BANK_ENTERPRISE")
    )

    assert authorizer(ok) is True
    assert authorizer(missing_task) is False
    assert authorizer(wrong_user) is False
    assert authorizer(wrong_flow) is False
    assert authorizer(wrong_scenario) is False


def test_permission_denied_external_result_is_identical_for_missing_and_cross_user() -> None:
    task_service = TaskService()
    transaction_service = TransactionService()
    _seed_task(task_service, user_id="owner", task_id="T_EXT", scenario_type="BANK_CLEARING")
    _seed_clearing_transactions(transaction_service, user_id="owner", task_id="T_EXT")

    authorizer = make_tenant_authorizer(
        task_service=task_service,
        transaction_service=transaction_service,
    )
    registry = build_default_registry(
        transaction_service=transaction_service,
    )
    executor = _executor(registry, authorizer)

    missing = executor.execute(
        "lookup_t1_context",
        LookupT1ContextArgs(),
        _ctx(user_id="owner", task_id="NOPE", flow_id="CLEAR_CUTOFF"),
    )
    cross_user = executor.execute(
        "lookup_t1_context",
        LookupT1ContextArgs(),
        _ctx(user_id="intruder", task_id="T_EXT", flow_id="CLEAR_CUTOFF"),
    )

    assert missing.status == cross_user.status == "FAILED"
    assert missing.error_type == cross_user.error_type == "PERMISSION_DENIED"
    assert missing.fallback_reason == cross_user.fallback_reason == "TOOL_ACCESS_DENIED"


# --------------------------------------------------------------------------- #
# Infra fault injection at adapter data layer
# --------------------------------------------------------------------------- #


def test_lookup_t1_context_redis_error_reraised_not_arq_business_failure() -> None:
    class _FaultyTransactions:
        def flow_belongs_to_task(self, **kwargs: object) -> bool:
            return True

        def get_clear_row(self, **kwargs: object) -> dict[str, object] | None:
            raise RedisConnectionError("redis gone")

        def list_bank_rows(self, **kwargs: object) -> list[dict[str, object]]:
            return []

    registry = build_default_registry(
        transaction_service=_FaultyTransactions(),
    )
    executor = _executor(registry, lambda ctx: True)

    with pytest.raises(RedisConnectionError):
        executor.execute(
            "lookup_t1_context",
            LookupT1ContextArgs(),
            _ctx(task_id="T_X", flow_id="CLEAR_CUTOFF"),
        )


def test_make_search_rules_adapter_signals_circuit_open() -> None:
    breaker = CircuitBreaker(fail_threshold=1, open_seconds=30, time_fn=lambda: 0.0)
    breaker.record_failure()
    adapter = make_search_rules_adapter(
        retriever=_StubRetriever(RagSearchResponse(items=[], rewritten_query=None)),
        rag_breaker=breaker,
    )
    from bank_reconciliation_agent.schemas.tools import ToolContext

    with pytest.raises(CircuitOpenError):
        adapter(SearchRulesArgs(query="x"), ToolContext(**_ctx()))
