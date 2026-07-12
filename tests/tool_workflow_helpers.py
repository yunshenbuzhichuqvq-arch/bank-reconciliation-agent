from __future__ import annotations

from datetime import date
from typing import Any

from bank_reconciliation_agent.schemas.rag import RagSearchRequest, RagSearchResponse
from bank_reconciliation_agent.schemas.tools import (
    ConfirmedCase,
    ConfirmedCasesOutput,
    SearchRulesOutput,
    T1ContextOutput,
    ToolAttemptRecord,
    ToolCallResult,
    ToolContext,
)


def succeeded(tool_name: str, result: object) -> ToolCallResult:
    return ToolCallResult(
        tool_name=tool_name,
        status="SUCCEEDED",
        result=result,
        attempt=1,
        duration_ms=1.0,
        attempts=[ToolAttemptRecord(attempt=1, status="SUCCEEDED", duration_ms=1.0)],
    )


def empty(tool_name: str) -> ToolCallResult:
    return ToolCallResult(
        tool_name=tool_name,
        status="EMPTY",
        attempt=1,
        duration_ms=1.0,
        attempts=[ToolAttemptRecord(attempt=1, status="EMPTY", duration_ms=1.0)],
    )


def failed(tool_name: str, error_type: str, fallback_reason: str) -> ToolCallResult:
    return ToolCallResult(
        tool_name=tool_name,
        status="FAILED",
        error_type=error_type,
        fallback_reason=fallback_reason,
        retryable=False,
        attempt=1,
        duration_ms=1.0,
        attempts=[
            ToolAttemptRecord(attempt=1, status="FAILED", duration_ms=1.0, error_type=error_type)
        ],
    )


class RetrieverBackedToolExecutor:
    """Test executor that routes the three tools to legacy stub collaborators.

    ``search_rules`` delegates to a ``retriever.search()`` stub, mirroring the
    pre-Stage-28 direct injection. Retriever exceptions become a FAILED result so
    that legacy "breaker open / retrieval error -> human" expectations survive the
    migration. ``load_confirmed_cases`` delegates to a fallback provider, and
    ``lookup_t1_context`` returns a canned T+1 result.
    """

    def __init__(
        self,
        *,
        retriever: Any = None,
        fallback_case_provider: Any = None,
        t1_result: ToolCallResult | None = None,
    ) -> None:
        self._retriever = retriever
        self._fallback_case_provider = fallback_case_provider
        self._t1_result = t1_result
        self.requests: list[RagSearchRequest] = []

    def execute(self, name: str, args: Any, context: ToolContext) -> ToolCallResult:
        if name == "search_rules":
            return self._search_rules(args, context)
        if name == "load_confirmed_cases":
            return self._load_confirmed_cases(context)
        if name == "lookup_t1_context":
            return self._lookup_t1_context()
        raise AssertionError(f"unexpected tool: {name}")

    def _search_rules(self, args: Any, context: ToolContext) -> ToolCallResult:
        from bank_reconciliation_agent.core.config import settings

        request = RagSearchRequest(
            query=args.query,
            top_k=settings.rag_rerank_top_k,
            min_score=_min_score(self._retriever),
            scenario_type=context.scenario_type,
            enable_rewrite=settings.enable_rag_rewrite,
            enable_hybrid=settings.enable_rag_hybrid,
            enable_reranker=settings.enable_rag_reranker,
        )
        self.requests.append(request)
        try:
            response: RagSearchResponse = self._retriever.search(request)
        except Exception as exc:  # noqa: BLE001 - legacy breaker/error path -> human
            return failed("search_rules", "INTERNAL_ERROR", f"TOOL_INTERNAL_ERROR:{type(exc).__name__}")
        if not response.items:
            return empty("search_rules")
        return succeeded(
            "search_rules",
            SearchRulesOutput(items=list(response.items), rewritten_query=response.rewritten_query),
        )

    def _load_confirmed_cases(self, context: ToolContext) -> ToolCallResult:
        if self._fallback_case_provider is None:
            return empty("load_confirmed_cases")
        rows = self._fallback_case_provider.confirmed_cases(
            user_id=context.user_id,
            exception_branch=context.exception_branch,
            limit=3,
        )
        if not rows:
            return empty("load_confirmed_cases")
        return succeeded(
            "load_confirmed_cases",
            ConfirmedCasesOutput(items=[ConfirmedCase.model_validate(row) for row in rows]),
        )

    def _lookup_t1_context(self) -> ToolCallResult:
        if self._t1_result is not None:
            return self._t1_result
        return empty("lookup_t1_context")


def t1_succeeded(flow_id: str, accounting_date: str) -> ToolCallResult:
    return succeeded(
        "lookup_t1_context",
        T1ContextOutput(flow_id=flow_id, accounting_date=date.fromisoformat(accounting_date)),
    )


def _min_score(retriever: Any) -> float:
    from bank_reconciliation_agent.core.config import settings

    store = getattr(retriever, "store", None)
    backend = getattr(store, "embedding_backend", None)
    return settings.rag_dense_min_score_for_backend(backend if isinstance(backend, str) else "hash")
