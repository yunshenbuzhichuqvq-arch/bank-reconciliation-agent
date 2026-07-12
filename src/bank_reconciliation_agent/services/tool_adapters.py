from __future__ import annotations

from typing import Callable, Protocol

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.rag.retriever import rule_retriever
from bank_reconciliation_agent.schemas.rag import RagSearchRequest
from bank_reconciliation_agent.schemas.tools import (
    ConfirmedCase,
    ConfirmedCasesOutput,
    LoadConfirmedCasesArgs,
    LookupT1ContextArgs,
    SearchRulesArgs,
    SearchRulesOutput,
    T1ContextOutput,
    ToolContext,
)
from bank_reconciliation_agent.services.circuit_breaker import CircuitBreaker
from bank_reconciliation_agent.services.exception_router import find_t1_candidate
from bank_reconciliation_agent.services.fallback import (
    LedgerFallbackCaseProvider,
    ledger_fallback_case_provider,
)
from bank_reconciliation_agent.services.task import task_service
from bank_reconciliation_agent.services.tool_executor import (
    TOOL_POLICIES,
    CircuitOpenError,
    ToolDefinition,
    ToolExecutor,
)
from bank_reconciliation_agent.services.transactions import (
    TransactionService,
    transaction_service,
)


class _Retriever(Protocol):
    def search(self, request: RagSearchRequest): ...


class _TaskLookup(Protocol):
    def get(self, *, user_id: str, task_id: str): ...


class _FlowLookup(Protocol):
    def flow_belongs_to_task(self, *, user_id: str, task_id: str, flow_id: str) -> bool: ...


def _effective_embedding_backend(retriever: _Retriever) -> str | None:
    store = getattr(retriever, "store", None)
    backend = getattr(store, "embedding_backend", None)
    return backend if isinstance(backend, str) else "hash"


def make_search_rules_adapter(
    *,
    retriever: _Retriever = rule_retriever,
    rag_breaker: CircuitBreaker,
) -> Callable[[SearchRulesArgs, ToolContext], SearchRulesOutput]:
    def adapter(args: SearchRulesArgs, context: ToolContext) -> SearchRulesOutput:
        if not rag_breaker.allow_request():
            raise CircuitOpenError("rag circuit breaker open")

        request = RagSearchRequest(
            query=args.query,
            top_k=settings.rag_rerank_top_k,
            min_score=settings.rag_dense_min_score_for_backend(
                _effective_embedding_backend(retriever)
            ),
            scenario_type=context.scenario_type,
            enable_rewrite=settings.enable_rag_rewrite,
            enable_hybrid=settings.enable_rag_hybrid,
            enable_reranker=settings.enable_rag_reranker,
        )
        try:
            response = retriever.search(request)
        except Exception:
            rag_breaker.record_failure()
            raise

        rag_breaker.record_success()
        return SearchRulesOutput(items=list(response.items), rewritten_query=response.rewritten_query)

    return adapter


def make_load_confirmed_cases_adapter(
    *,
    case_provider: LedgerFallbackCaseProvider = ledger_fallback_case_provider,
) -> Callable[[LoadConfirmedCasesArgs, ToolContext], ConfirmedCasesOutput]:
    def adapter(args: LoadConfirmedCasesArgs, context: ToolContext) -> ConfirmedCasesOutput:
        del args
        rows = case_provider.confirmed_cases(
            user_id=context.user_id,
            exception_branch=context.exception_branch,
            limit=3,
        )
        return ConfirmedCasesOutput(items=[ConfirmedCase.model_validate(row) for row in rows])

    return adapter


def make_lookup_t1_context_adapter(
    *,
    transaction_service: TransactionService = transaction_service,
) -> Callable[[LookupT1ContextArgs, ToolContext], T1ContextOutput | None]:
    def adapter(args: LookupT1ContextArgs, context: ToolContext) -> T1ContextOutput | None:
        del args
        clear_row = transaction_service.get_clear_row(
            user_id=context.user_id,
            task_id=context.task_id,
            flow_id=context.flow_id,
        )
        if clear_row is None:
            return None
        bank_rows = transaction_service.list_bank_rows(
            user_id=context.user_id,
            task_id=context.task_id,
        )
        candidate = find_t1_candidate(clear_row, bank_rows)
        if candidate is None:
            return None
        return T1ContextOutput.model_validate(candidate)

    return adapter


def make_tenant_authorizer(
    *,
    task_service: _TaskLookup = task_service,
    transaction_service: _FlowLookup = transaction_service,
) -> Callable[[ToolContext], bool]:
    def authorizer(context: ToolContext) -> bool:
        task = task_service.get(user_id=context.user_id, task_id=context.task_id)
        if task is None or task.scenario_type != context.scenario_type:
            return False
        return transaction_service.flow_belongs_to_task(
            user_id=context.user_id,
            task_id=context.task_id,
            flow_id=context.flow_id,
        )

    return authorizer


def _search_rules_scenario(context: ToolContext) -> bool:
    return context.scenario_type in ("BANK_ENTERPRISE", "BANK_CLEARING")


def _load_confirmed_cases_scenario(context: ToolContext) -> bool:
    return context.fallback_level == 2


def _lookup_t1_context_scenario(context: ToolContext) -> bool:
    return context.scenario_type == "BANK_CLEARING" and context.exception_branch == "BC-R003"


def build_default_registry(
    *,
    retriever: _Retriever = rule_retriever,
    rag_breaker: CircuitBreaker | None = None,
    ledger_service: LedgerFallbackCaseProvider | None = None,
    transaction_service: TransactionService = transaction_service,
) -> dict[str, ToolDefinition]:
    breaker = rag_breaker or CircuitBreaker(
        fail_threshold=settings.rag_breaker_fail_threshold,
        open_seconds=settings.rag_breaker_open_seconds,
    )
    case_provider = ledger_service or ledger_fallback_case_provider
    return {
        "search_rules": ToolDefinition(
            name="search_rules",
            input_schema=SearchRulesArgs,
            output_schema=SearchRulesOutput,
            adapter=make_search_rules_adapter(retriever=retriever, rag_breaker=breaker),
            scenario_predicate=_search_rules_scenario,
            policy=TOOL_POLICIES["search_rules"],
        ),
        "load_confirmed_cases": ToolDefinition(
            name="load_confirmed_cases",
            input_schema=LoadConfirmedCasesArgs,
            output_schema=ConfirmedCasesOutput,
            adapter=make_load_confirmed_cases_adapter(case_provider=case_provider),
            scenario_predicate=_load_confirmed_cases_scenario,
            policy=TOOL_POLICIES["load_confirmed_cases"],
        ),
        "lookup_t1_context": ToolDefinition(
            name="lookup_t1_context",
            input_schema=LookupT1ContextArgs,
            output_schema=T1ContextOutput,
            adapter=make_lookup_t1_context_adapter(transaction_service=transaction_service),
            scenario_predicate=_lookup_t1_context_scenario,
            policy=TOOL_POLICIES["lookup_t1_context"],
        ),
    }


def build_default_tool_executor() -> ToolExecutor:
    authorizer = make_tenant_authorizer(
        task_service=task_service,
        transaction_service=transaction_service,
    )
    return ToolExecutor(build_default_registry(), authorizer)


default_tool_executor = build_default_tool_executor()
