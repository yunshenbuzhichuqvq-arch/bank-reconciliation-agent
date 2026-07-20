from __future__ import annotations

from decimal import Decimal
from typing import NamedTuple

from bank_reconciliation_agent.core.llm.cost import compute_cost
from bank_reconciliation_agent.schemas.ledger import LedgerRow
from bank_reconciliation_agent.schemas.trace import TraceSpan


class ReconciliationMatchSummary(NamedTuple):
    auto_fixed_rows: int
    pending_ai_rows: int
    pending_human_rows: int


class ReconciliationMatchResult(NamedTuple):
    flow_id: str
    status: str
    error_type: str | None
    exception_branch: str | None
    bank_amount: Decimal | None
    clear_amount: Decimal | None
    amount_diff: Decimal | None
    t1_candidate: dict[str, str] | None = None
    fuzzy_candidate: dict[str, str] | None = None


class ReconciliationWriteBundle(NamedTuple):
    ledger_rows: list[LedgerRow]
    rag_log_rows: list[dict[str, object]]
    agent_log_rows: list[dict[str, object]]
    trace_snapshots: list[tuple[str, str, list[TraceSpan]]]
    ai_processed_rows: int
    fallback_l2_rows: int
    fallback_l3_rows: int
    total_prompt_tokens: int
    total_completion_tokens: int
    saved_prompt_tokens: int = 0
    saved_completion_tokens: int = 0

    @property
    def saved_cost(self) -> Decimal:
        return compute_cost(self.saved_prompt_tokens, self.saved_completion_tokens)


class ReconciliationFlowBundle(NamedTuple):
    ledger_row: LedgerRow
    rag_log_row: dict[str, object]
    agent_log_row: dict[str, object]
    trace_snapshot: tuple[str, str, list[TraceSpan]] | None
    prompt_tokens: int
    completion_tokens: int
    saved_prompt_tokens: int
    saved_completion_tokens: int
    fallback_l2_rows: int
    fallback_l3_rows: int
    stream_seq: int
