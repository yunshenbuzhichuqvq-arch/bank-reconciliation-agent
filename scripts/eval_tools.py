from __future__ import annotations

import argparse
import json
import math
import os
import platform
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from threading import Event
from typing import Any, Callable

# Force a deterministic, offline, hash-embedding boundary before importing any
# repo RAG/Tool module. Importing tool_adapters constructs a default retriever
# that would otherwise read an external EMBEDDING_BACKEND and load models or
# contact the Hugging Face Hub. This must run before the imports below.
os.environ["EMBEDDING_BACKEND"] = "hash"

import pandas as pd  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

from bank_reconciliation_agent.rag.retriever import ChromaRuleStore, RuleRetriever  # noqa: E402
from bank_reconciliation_agent.schemas.tools import (  # noqa: E402
    LoadConfirmedCasesArgs,
    LookupT1ContextArgs,
    SearchRulesArgs,
    SearchRulesOutput,
    ToolCallResult,
    ToolContext,
)
from bank_reconciliation_agent.services.fallback import LedgerFallbackCaseProvider  # noqa: E402
from bank_reconciliation_agent.services.ledger import LedgerService  # noqa: E402
from bank_reconciliation_agent.schemas.ledger import LedgerRow  # noqa: E402
from bank_reconciliation_agent.services.task import TaskService  # noqa: E402
from bank_reconciliation_agent.services.tool_adapters import (  # noqa: E402
    build_default_registry,
    make_search_rules_adapter,
    make_tenant_authorizer,
)
from bank_reconciliation_agent.services.circuit_breaker import CircuitBreaker  # noqa: E402
from bank_reconciliation_agent.services.tool_executor import (  # noqa: E402
    TOOL_POLICIES,
    ToolDefinition,
    ToolExecutor,
    ToolPolicy,
    ToolTransientError,
    safe_tool_projection,
)
from bank_reconciliation_agent.services.transactions import TransactionService  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON_REPORT_PATH = PROJECT_ROOT / "reports/tool_executor_evidence.json"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "reports/tool_executor_evidence.md"

STAGE = "stage-28-readonly-tool-executor"
CLEARING_CHUNKS_PATH = PROJECT_ROOT / "data/rag/rule_chunks_bank_clearing.jsonl"
ENTERPRISE_CHUNKS_PATH = PROJECT_ROOT / "data/rag/rule_chunks_bank_enterprise.jsonl"

SENSITIVE_QUERY_MARKER = "SENSITIVE_QUERY_MARKER_DO_NOT_LEAK"
SENSITIVE_RULE_MARKER = "SENSITIVE_RULE_BODY_DO_NOT_LEAK"
SENSITIVE_OPINION_MARKER = "SENSITIVE_AUDIT_OPINION_DO_NOT_LEAK"

# Deterministic query that scores below the hash-embedding evidence floor, so the
# real retriever returns zero items (a genuine EMPTY, not an injected failure).
NO_EVIDENCE_QUERY = "no_evidence_probe_zzq"

_OWNER = "eval_owner"
_TASK = "EVAL_TASK"


def percentile(samples: list[float], p: float) -> float:
    """Nearest-rank percentile: index = max(0, ceil(p * n) - 1) on ascending samples."""
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = max(0, math.ceil(p * len(ordered)) - 1)
    return round(ordered[index], 3)


class _BlockingTimeoutAdapter:
    """Deterministic fault adapter that always outlives the injected timeout."""

    def __init__(self, release: Event) -> None:
        self._release = release

    def __call__(self, args: Any, context: ToolContext) -> Any:
        self._release.wait(timeout=2.0)
        return SearchRulesOutput(items=[])


class _TransientThenSucceedAdapter:
    """Fault adapter that raises a transient error once, then returns a real hit."""

    def __init__(self, real_adapter: Callable[[Any, ToolContext], Any]) -> None:
        self._real_adapter = real_adapter
        self._calls = 0

    def __call__(self, args: Any, context: ToolContext) -> Any:
        self._calls += 1
        if self._calls == 1:
            raise ToolTransientError("transient read error (fault injection)")
        return self._real_adapter(args, context)


class _EvalFixture:
    def __init__(self, root: Path) -> None:
        db_path = root / "eval_tools.sqlite"
        self.engine = create_engine(f"sqlite:///{db_path}", future=True)
        self.task_service = TaskService(self.engine)
        self.transaction_service = TransactionService(self.engine)
        self.ledger_service = LedgerService(self.engine)
        self.case_provider = LedgerFallbackCaseProvider(self.engine)
        self.retriever = RuleRetriever(
            store=ChromaRuleStore(
                chunks_path=CLEARING_CHUNKS_PATH,
                chroma_path=root / "chroma",
                embedding_backend="hash",
            )
        )
        self.breaker = CircuitBreaker(fail_threshold=1, open_seconds=30, time_fn=lambda: 0.0)
        self.registry = build_default_registry(
            retriever=self.retriever,
            rag_breaker=self.breaker,
            ledger_service=self.case_provider,
            transaction_service=self.transaction_service,
        )
        self.authorizer = make_tenant_authorizer(
            task_service=self.task_service,
            transaction_service=self.transaction_service,
        )
        self.executor = ToolExecutor(
            self.registry,
            self.authorizer,
            sleeper=lambda seconds: None,
        )
        self._seed()

    def _seed(self) -> None:
        self.task_service.replace_task(
            user_id=_OWNER,
            task_id=_TASK,
            scenario_type="BANK_CLEARING",
            total_bank_rows=1,
            total_clear_rows=2,
            auto_fixed_rows=0,
            pending_ai_rows=0,
            pending_human_rows=2,
        )
        bank_df = pd.DataFrame(
            [
                {
                    "flow_id": "CORE_T1",
                    "amount": Decimal("100.00"),
                    "debit_amount": Decimal("0.00"),
                    "credit_amount": Decimal("100.00"),
                    "trade_time": datetime(2026, 6, 11, 10, 0, 0),
                    "accounting_date": date(2026, 6, 11),
                    "summary": "核心 T+1 入账",
                    "reference_no": "REF-100",
                    "merchant_order_no": None,
                    "voucher_no": None,
                }
            ]
        )
        clear_df = pd.DataFrame(
            [
                {
                    "flow_id": "CLEAR_CUTOFF",
                    "amount": Decimal("100.00"),
                    "transaction_amount": Decimal("100.00"),
                    "net_amount": Decimal("100.00"),
                    "trade_time": datetime(2026, 6, 10, 23, 30, 0),
                    "trade_date": date(2026, 6, 10),
                    "summary": "清算跨日切",
                    "reference_no": "REF-100",
                },
                {
                    "flow_id": "CLEAR_NOMATCH",
                    "amount": Decimal("55.00"),
                    "transaction_amount": Decimal("55.00"),
                    "net_amount": Decimal("55.00"),
                    "trade_time": datetime(2026, 6, 10, 23, 45, 0),
                    "trade_date": date(2026, 6, 10),
                    "summary": "清算跨日切无匹配",
                    "reference_no": "REF-NONE",
                },
            ]
        )
        self.transaction_service.replace_task_rows(
            user_id=_OWNER,
            task_id=_TASK,
            bank_df=bank_df,
            clear_df=clear_df,
        )
        self.ledger_service.replace_task_rows(
            user_id=_OWNER,
            task_id=_TASK,
            scenario_type="BANK_CLEARING",
            rows=[
                LedgerRow(
                    id=0,
                    task_id=_TASK,
                    flow_id="CLEAR_CUTOFF",
                    error_type="CUTOFF_CROSS_DAY",
                    exception_branch="BC-R003",
                    bank_amount=Decimal("100.00"),
                    clear_amount=Decimal("100.00"),
                    discrepancy_amount=Decimal("0.00"),
                    ai_audit_opinion=SENSITIVE_OPINION_MARKER,
                    ai_confidence=Decimal("0.9000"),
                    rag_source=None,
                    handle_status="FIXED",
                )
            ],
        )

    def context(self, **overrides: object) -> ToolContext:
        base: dict[str, object] = {
            "user_id": _OWNER,
            "task_id": _TASK,
            "flow_id": "CLEAR_CUTOFF",
            "scenario_type": "BANK_CLEARING",
            "exception_branch": "BC-R003",
            "fallback_level": 0,
        }
        base.update(overrides)
        return ToolContext(**base)


def _case_row(
    *,
    label: str,
    tool_name: str,
    source: str,
    result: ToolCallResult,
) -> dict[str, Any]:
    projection = safe_tool_projection(result)
    return {
        "label": label,
        "source": source,
        **projection,
    }


def _collect_cases(fixture: _EvalFixture) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    executor = fixture.executor

    # --- real adapter SUCCEEDED + EMPTY for each tool ---
    cases.append(
        _case_row(
            label="search_rules_real_succeeded",
            tool_name="search_rules",
            source="real_adapter",
            result=executor.execute(
                "search_rules",
                SearchRulesArgs(query="跨日切 T+1 补记 清算 单边 查询查复"),
                fixture.context(),
            ),
        )
    )
    cases.append(
        _case_row(
            label="search_rules_real_empty",
            tool_name="search_rules",
            source="real_adapter",
            result=executor.execute(
                "search_rules",
                SearchRulesArgs(query=NO_EVIDENCE_QUERY),
                fixture.context(),
            ),
        )
    )
    cases.append(
        _case_row(
            label="load_confirmed_cases_real_succeeded",
            tool_name="load_confirmed_cases",
            source="real_adapter",
            result=executor.execute(
                "load_confirmed_cases",
                LoadConfirmedCasesArgs(),
                fixture.context(fallback_level=2, exception_branch="BC-R003"),
            ),
        )
    )
    cases.append(
        _case_row(
            label="load_confirmed_cases_real_empty",
            tool_name="load_confirmed_cases",
            source="real_adapter",
            result=executor.execute(
                "load_confirmed_cases",
                LoadConfirmedCasesArgs(),
                fixture.context(fallback_level=2, exception_branch="BC-R404"),
            ),
        )
    )
    cases.append(
        _case_row(
            label="lookup_t1_context_real_succeeded",
            tool_name="lookup_t1_context",
            source="real_adapter",
            result=executor.execute(
                "lookup_t1_context",
                LookupT1ContextArgs(),
                fixture.context(flow_id="CLEAR_CUTOFF"),
            ),
        )
    )
    cases.append(
        _case_row(
            label="lookup_t1_context_real_empty",
            tool_name="lookup_t1_context",
            source="real_adapter",
            result=executor.execute(
                "lookup_t1_context",
                LookupT1ContextArgs(),
                fixture.context(flow_id="CLEAR_NOMATCH"),
            ),
        )
    )

    # --- input validation failure (extra identity field) ---
    cases.append(
        _case_row(
            label="search_rules_validation_error",
            tool_name="search_rules",
            source="real_adapter",
            result=executor.execute(
                "search_rules",
                {"query": "跨日切", "user_id": "attacker"},
                fixture.context(),
            ),
        )
    )

    # --- permission denied: missing task and cross-user are indistinguishable ---
    cases.append(
        _case_row(
            label="lookup_t1_permission_missing_task",
            tool_name="lookup_t1_context",
            source="real_adapter",
            result=executor.execute(
                "lookup_t1_context",
                LookupT1ContextArgs(),
                fixture.context(task_id="NO_SUCH_TASK"),
            ),
        )
    )
    cases.append(
        _case_row(
            label="lookup_t1_permission_cross_user",
            tool_name="lookup_t1_context",
            source="real_adapter",
            result=executor.execute(
                "lookup_t1_context",
                LookupT1ContextArgs(),
                fixture.context(user_id="intruder"),
            ),
        )
    )

    # --- final TIMEOUT after two physical attempts (fault injection) ---
    cases.append(_timeout_case(fixture))

    # --- retry recovery: transient then real success (fault injection) ---
    cases.append(_retry_recovered_case(fixture))

    # --- breaker OPEN -> CIRCUIT_OPEN (fault injection) ---
    cases.append(_circuit_open_case(fixture))

    return cases


def _timeout_case(fixture: _EvalFixture) -> dict[str, Any]:
    release = Event()
    pool = ThreadPoolExecutor(max_workers=2)
    try:
        registry = {
            "search_rules": ToolDefinition(
                name="search_rules",
                input_schema=SearchRulesArgs,
                output_schema=SearchRulesOutput,
                adapter=_BlockingTimeoutAdapter(release),
                scenario_predicate=lambda ctx: True,
                policy=ToolPolicy(timeout_s=0.02, max_attempts=2, backoff_s=0.0),
            )
        }
        executor = ToolExecutor(
            registry,
            fixture.authorizer,
            executor=pool,
            sleeper=lambda seconds: None,
        )
        result = executor.execute("search_rules", SearchRulesArgs(query="timeout"), fixture.context())
    finally:
        release.set()
        pool.shutdown(wait=True)
    return _case_row(
        label="search_rules_timeout_exhausted",
        tool_name="search_rules",
        source="fault_injection",
        result=result,
    )


def _retry_recovered_case(fixture: _EvalFixture) -> dict[str, Any]:
    real_adapter = make_search_rules_adapter(
        retriever=fixture.retriever,
        rag_breaker=CircuitBreaker(fail_threshold=1, open_seconds=30, time_fn=lambda: 0.0),
    )
    registry = {
        "search_rules": ToolDefinition(
            name="search_rules",
            input_schema=SearchRulesArgs,
            output_schema=SearchRulesOutput,
            adapter=_TransientThenSucceedAdapter(real_adapter),
            scenario_predicate=lambda ctx: True,
            policy=TOOL_POLICIES["search_rules"],
        )
    }
    executor = ToolExecutor(registry, fixture.authorizer, sleeper=lambda seconds: None)
    result = executor.execute(
        "search_rules",
        SearchRulesArgs(query="跨日切 T+1 补记 清算 单边 查询查复"),
        fixture.context(),
    )
    return _case_row(
        label="search_rules_retry_recovered",
        tool_name="search_rules",
        source="fault_injection",
        result=result,
    )


def _circuit_open_case(fixture: _EvalFixture) -> dict[str, Any]:
    breaker = CircuitBreaker(fail_threshold=1, open_seconds=30, time_fn=lambda: 0.0)
    breaker.record_failure()  # force OPEN
    registry = build_default_registry(
        retriever=fixture.retriever,
        rag_breaker=breaker,
        ledger_service=fixture.case_provider,
        transaction_service=fixture.transaction_service,
    )
    executor = ToolExecutor(registry, fixture.authorizer, sleeper=lambda seconds: None)
    result = executor.execute(
        "search_rules",
        SearchRulesArgs(query="跨日切 T+1 补记"),
        fixture.context(),
    )
    return _case_row(
        label="search_rules_circuit_open",
        tool_name="search_rules",
        source="fault_injection",
        result=result,
    )


def _summarize_tool(cases: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes: dict[str, int] = {}
    errors: dict[str, int] = {}
    retry_recovered = 0
    durations: list[float] = []
    for case in cases:
        outcomes[case["status"]] = outcomes.get(case["status"], 0) + 1
        if case["error_type"]:
            errors[case["error_type"]] = errors.get(case["error_type"], 0) + 1
        if case["retry_recovered"]:
            retry_recovered += 1
        durations.append(float(case["duration_ms"]))
    return {
        "outcomes": outcomes,
        "errors": errors,
        "retry_recovered": retry_recovered,
        "latency_ms": {
            "p50": percentile(durations, 0.5),
            "p95": percentile(durations, 0.95),
            "sample_count": len(durations),
        },
    }


def build_report() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="eval_tools_") as tmp:
        fixture = _EvalFixture(Path(tmp))
        cases = _collect_cases(fixture)

    tools: dict[str, Any] = {}
    for tool_name in ("search_rules", "load_confirmed_cases", "lookup_t1_context"):
        tool_cases = [c for c in cases if c["tool_name"] == tool_name]
        tools[tool_name] = _summarize_tool(tool_cases)

    return {
        "stage": STAGE,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "embedding_backend": "hash",
            "database": "sqlite",
            "rag_backend": "chromadb",
        },
        "claim_boundary": {
            "local_only": True,
            "sqlite": True,
            "hash_embedding": True,
            "external_credentials": False,
            "network_access": False,
            "production_sla": False,
            "note": (
                "Deterministic local evidence only; latency is an observation, not a "
                "production SLA or cross-machine benchmark."
            ),
        },
        "case_count": len(cases),
        "tools": tools,
        "cases": cases,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Stage 28 只读 Tool Executor 离线证据")
    lines.append("")
    lines.append(f"- Stage: `{summary['stage']}`")
    lines.append(f"- Evaluated at: {summary['evaluated_at']}")
    lines.append(f"- Case count: {summary['case_count']}")
    lines.append("")
    env = summary["environment"]
    lines.append("## 环境与 Claim Boundary")
    lines.append("")
    lines.append(f"- Python: {env['python']}")
    lines.append(f"- Platform: {env['platform']}")
    lines.append(f"- Embedding backend: {env['embedding_backend']}")
    lines.append(f"- Database: {env['database']}")
    lines.append(
        "- 仅本地 SQLite + hash embedding，无外网、无外部凭证、非生产 SLA；"
        "latency 仅为本地观察值，不设 pass gate。"
    )
    lines.append("")
    lines.append("## 按 Tool 的 outcome / error / retry / latency")
    lines.append("")
    lines.append("| Tool | Outcomes | Errors | Retry recovered | P50 ms (obs) | P95 ms (obs) | Samples |")
    lines.append("| --- | --- | --- | ---: | ---: | ---: | ---: |")
    for tool_name, stats in summary["tools"].items():
        latency = stats["latency_ms"]
        lines.append(
            f"| `{tool_name}` | {_fmt_counts(stats['outcomes'])} | "
            f"{_fmt_counts(stats['errors']) or '-'} | {stats['retry_recovered']} | "
            f"{latency['p50']} | {latency['p95']} | {latency['sample_count']} |"
        )
    lines.append("")
    lines.append("## Case 安全投影")
    lines.append("")
    lines.append("| Label | Tool | Source | Status | Error | Fallback | Attempt | Retry recovered | Result count | Evidence IDs |")
    lines.append("| --- | --- | --- | --- | --- | --- | ---: | :---: | ---: | --- |")
    for case in summary["cases"]:
        evidence = ", ".join(str(x) for x in case["evidence_ids"]) or "-"
        lines.append(
            f"| {case['label']} | `{case['tool_name']}` | {case['source']} | "
            f"{case['status']} | {case['error_type'] or '-'} | {case['fallback_reason'] or '-'} | "
            f"{case['attempt']} | {'yes' if case['retry_recovered'] else 'no'} | "
            f"{case['result_count']} | {evidence} |"
        )
    return "\n".join(lines) + "\n"


def _fmt_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))


def run(
    *,
    json_report: Path | None = None,
    report: Path | None = None,
) -> dict[str, Any]:
    json_path = json_report or DEFAULT_JSON_REPORT_PATH
    report_path = report or DEFAULT_REPORT_PATH
    summary = build_report()
    markdown = render_markdown(summary)

    json_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(markdown, encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate deterministic local evidence for the Stage 28 readonly tools.",
    )
    parser.add_argument("--json-report", type=Path, default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args(argv)

    summary = run(json_report=args.json_report, report=args.report)
    print(f"stage={summary['stage']} case_count={summary['case_count']}")
    print(f"json_report={args.json_report}")
    print(f"report={args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
