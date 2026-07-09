from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.rag.scoring import representative_score
from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchRequest

RuleRetriever: Any | None = None
ChromaRuleStore: Any | None = None

_retriever_classes: tuple[Any, Any] | None = None


def _get_retriever_classes() -> tuple[Any, Any]:
    global _retriever_classes
    if RuleRetriever is not None and ChromaRuleStore is not None:
        return RuleRetriever, ChromaRuleStore
    if _retriever_classes is None:
        from bank_reconciliation_agent.rag.retriever import ChromaRuleStore as _C
        from bank_reconciliation_agent.rag.retriever import RuleRetriever as _R

        _retriever_classes = (_R, _C)
    return _retriever_classes


def _get_rule_retriever() -> Any:
    from bank_reconciliation_agent.rag.retriever import rule_retriever as _r

    return _r


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVAL_SET_PATH = PROJECT_ROOT / "data/rag_eval_set.json"
DEFAULT_CHUNKS_PATH = PROJECT_ROOT / "data/rag/rule_chunks_bank_enterprise.jsonl"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "reports/rag_eval.md"
DEFAULT_JSON_REPORT_PATH = PROJECT_ROOT / "reports/rag_eval_metrics.json"
DEFAULT_COMPARISON_REPORT_PATH = PROJECT_ROOT / "reports/rag_eval_mode_comparison.md"
DEFAULT_COMPARISON_JSON_PATH = PROJECT_ROOT / "reports/rag_eval_mode_comparison.json"
DEFAULT_MATRIX_REPORT_PATH = PROJECT_ROOT / "reports/rag_quality_matrix.md"
DEFAULT_MATRIX_JSON_PATH = PROJECT_ROOT / "reports/rag_quality_matrix.json"
DEFAULT_OPTIMIZATION_COMPARISON_REPORT_PATH = PROJECT_ROOT / "reports/rag_optimization_comparison.md"
DEFAULT_OPTIMIZATION_COMPARISON_JSON_PATH = PROJECT_ROOT / "reports/rag_optimization_comparison.json"

RagEvalMode = Literal["dense", "hybrid", "hybrid_rerank"]
RagBackendMatrixStatus = Literal["measured", "not_run", "unavailable"]
RealBackendPolicy = Literal["skip", "auto"]


@dataclass(frozen=True)
class EvalCase:
    id: str
    scenario_type: str
    error_type: str
    query: str
    expected_chunk_ids: list[str]


@dataclass(frozen=True)
class EvalCaseResult:
    id: str
    scenario_type: str
    error_type: str
    query: str
    expected_chunk_ids: list[str]
    retrieved_chunk_ids: list[str]
    hit_at_1: float
    recall_at_5: float
    reciprocal_rank: float
    ndcg_at_5: float


@dataclass(frozen=True)
class ScenarioSummary:
    scenario_type: str
    case_count: int
    hit_at_1: float
    recall_at_5: float
    mrr: float
    ndcg_at_5: float


@dataclass(frozen=True)
class ErrorTypeSummary:
    scenario_type: str
    error_type: str
    case_count: int
    hit_at_1: float
    recall_at_5: float
    mrr: float
    ndcg_at_5: float


@dataclass(frozen=True)
class SmokeCase:
    query: str
    expected_tag: str


@dataclass(frozen=True)
class LegacyCaseResult:
    query: str
    expected_tag: str
    matched_chunk_id: str | None
    representative_score: float | None
    reranker_score: float | None
    hit: bool


@dataclass(frozen=True)
class LegacyEvalSummary:
    mode: str
    case_results: list[LegacyCaseResult]

    @property
    def hit_count(self) -> int:
        return sum(result.hit for result in self.case_results)

    @property
    def average_reranker_score(self) -> float:
        scores = [result.reranker_score for result in self.case_results if result.reranker_score is not None]
        if not scores:
            return 0.0
        return sum(scores) / len(scores)

SMOKE_CASES = [
    SmokeCase(query="金额差异 对账不平 银行端 清算端 金额", expected_tag="amount_mismatch"),
    SmokeCase(query="单边缺失 查询查复 来源文件", expected_tag="single_side_missing"),
    SmokeCase(query="差错 台账 审计 留痕 task_id flow_id", expected_tag="audit_trail"),
    SmokeCase(query="流水缺失 T+1 追溯 查询查复", expected_tag="single_side_missing"),
]


def load_eval_set(path: Path = DEFAULT_EVAL_SET_PATH) -> list[EvalCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [EvalCase(**item) for item in payload]


def request_for_eval_mode(
    case: EvalCase,
    *,
    mode: RagEvalMode,
    top_k: int,
    min_score: float = 0.0,
) -> RagSearchRequest:
    if mode == "dense":
        return RagSearchRequest(
            query=case.query,
            top_k=top_k,
            min_score=min_score,
            scenario_type=case.scenario_type,
            enable_hybrid=False,
            enable_reranker=False,
        )
    if mode == "hybrid":
        return RagSearchRequest(
            query=case.query,
            top_k=top_k,
            min_score=min_score,
            scenario_type=case.scenario_type,
            enable_hybrid=True,
            enable_reranker=False,
        )
    if mode == "hybrid_rerank":
        return RagSearchRequest(
            query=case.query,
            top_k=top_k,
            min_score=min_score,
            scenario_type=case.scenario_type,
            enable_hybrid=True,
            enable_reranker=True,
        )
    raise ValueError(f"unsupported eval mode: {mode}")


def evaluate_eval_set(
    cases: list[EvalCase],
    *,
    retriever: Any = None,
    top_k: int = 5,
    embedding_backend: str = "hash",
    mode: RagEvalMode = "dense",
) -> dict[str, Any]:
    if retriever is None:
        retriever = _get_rule_retriever()
    results = [
        _evaluate_case(case, retriever=retriever, top_k=top_k, min_score=0.0, mode=mode)
        for case in cases
    ]
    scenario_types = sorted({case.scenario_type for case in cases})
    summaries = [_summarize_scenario(results, scenario_type) for scenario_type in scenario_types]
    error_type_summaries = _summarize_by_error_type(results)
    global_metrics = _compute_global_metrics(summaries, len(cases))
    notes = _build_saturation_notes(global_metrics, summaries)
    return {
        "case_count": len(cases),
        "embedding_backend": embedding_backend,
        "top_k": top_k,
        "evaluated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "global_metrics": global_metrics,
        "notes": notes,
        "summaries": [asdict(summary) for summary in summaries],
        "error_type_summaries": [asdict(summary) for summary in error_type_summaries],
        "results": [asdict(result) for result in results],
    }


def evaluate_mode_comparison(
    cases: list[EvalCase],
    *,
    retriever: Any | None = None,
    modes: list[RagEvalMode] | None = None,
    top_k: int = 5,
    embedding_backend: str = "hash",
) -> dict[str, Any]:
    if modes is None:
        modes = ["dense", "hybrid", "hybrid_rerank"]
    if retriever is None:
        retriever = _get_rule_retriever()

    mode_reports: dict[str, dict[str, Any]] = {}
    for m in modes:
        mode_reports[m] = evaluate_eval_set(
            cases, retriever=retriever, top_k=top_k,
            embedding_backend=embedding_backend, mode=m,
        )

    dense_metrics = mode_reports["dense"]["global_metrics"]
    deltas: dict[str, dict[str, float]] = {}
    for m in modes:
        if m == "dense":
            continue
        gm = mode_reports[m]["global_metrics"]
        deltas[m] = {
            "hit_at_1": gm["hit_at_1"] - dense_metrics["hit_at_1"],
            "mrr": gm["mrr"] - dense_metrics["mrr"],
            "ndcg_at_5": gm["ndcg_at_5"] - dense_metrics["ndcg_at_5"],
        }

    selected_mode, selection_reason = _select_best_mode(modes, deltas, mode_reports)

    return {
        "embedding_backend": embedding_backend,
        "top_k": top_k,
        "case_count": len(cases),
        "evaluated_at": mode_reports[modes[0]]["evaluated_at"],
        "baseline_mode": "dense",
        "selected_mode": selected_mode,
        "selection_reason": selection_reason,
        "modes": {m: {
            "global_metrics": mode_reports[m]["global_metrics"],
            "bucket_metrics": _compute_bucket_metrics(mode_reports[m]),
        } for m in modes},
        "deltas_vs_dense": deltas,
    }


def _compute_bucket_metrics(report: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[EvalCaseResult] = [EvalCaseResult(**r) for r in report.get("results", [])]
    groups: dict[tuple[str, str], list[EvalCaseResult]] = {}
    for r in results:
        key = (r.scenario_type, r.error_type)
        groups.setdefault(key, []).append(r)

    buckets: list[dict[str, Any]] = []
    for (scenario_type, error_type), group in sorted(groups.items()):
        case_count = len(group)
        miss_count = sum(1 for r in group if r.recall_at_5 < 1.0)
        buckets.append(
            {
                "scenario_type": scenario_type,
                "error_type": error_type,
                "case_count": case_count,
                "miss_count": miss_count,
                "hit_at_1": sum(r.hit_at_1 for r in group) / case_count,
                "recall_at_5": sum(r.recall_at_5 for r in group) / case_count,
                "mrr": sum(r.reciprocal_rank for r in group) / case_count,
                "ndcg_at_5": sum(r.ndcg_at_5 for r in group) / case_count,
            }
        )
    return buckets


def _select_best_mode(
    modes: list[str],
    deltas: dict[str, dict[str, float]],
    mode_reports: dict[str, dict[str, Any]],
) -> tuple[str, str]:
    ranking_metrics = ["hit_at_1", "mrr", "ndcg_at_5"]
    eligible: list[str] = []
    for m in modes:
        if m == "dense":
            continue
        d = deltas[m]
        if any(d[k] < 0 for k in ranking_metrics):
            continue
        if not any(d[k] > 0 for k in ranking_metrics):
            continue
        eligible.append(m)

    if not eligible:
        return "dense", "No mode improved ranking metrics over dense baseline; RAG has no proven improvement"

    def _sort_key(m: str) -> tuple[float, float, float]:
        gm = mode_reports[m]["global_metrics"]
        return (gm["ndcg_at_5"], gm["mrr"], gm["hit_at_1"])

    best = max(eligible, key=_sort_key)
    return best, "Highest NDCG@5 among eligible modes with no negative ranking deltas"


def evaluate_backend_mode_matrix(
    cases: list[EvalCase],
    *,
    requested_backends: list[str] | None = None,
    modes: list[RagEvalMode] | None = None,
    top_k: int = 5,
    real_backend_policy: RealBackendPolicy = "skip",
    retriever_factory: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    if requested_backends is None:
        requested_backends = ["hash", "bge_small", "bge_m3"]
    if modes is None:
        modes = ["dense", "hybrid", "hybrid_rerank"]

    _R, _S = _get_retriever_classes()

    rows: dict[str, dict[str, Any]] = {}
    for backend in requested_backends:
        if real_backend_policy == "skip" and backend != "hash":
            rows[backend] = {
                "requested_backend": backend,
                "effective_backend": None,
                "status": "not_run",
                "reason": "real backend policy is skip",
            }
            continue

        retriever: Any = (
            retriever_factory(backend)
            if retriever_factory is not None
            else _R(store=_S(embedding_backend=backend))
        )

        effective_backend: str = getattr(retriever.store, "embedding_backend", backend)
        if effective_backend != backend:
            rows[backend] = {
                "requested_backend": backend,
                "effective_backend": effective_backend,
                "status": "unavailable",
                "reason": f"effective backend is {effective_backend}, not {backend}",
            }
            continue

        mode_report = evaluate_mode_comparison(
            cases,
            retriever=retriever,
            modes=modes,
            top_k=top_k,
            embedding_backend=effective_backend,
        )

        rows[backend] = {
            "requested_backend": backend,
            "effective_backend": effective_backend,
            "status": "measured",
            "selected_mode": mode_report["selected_mode"],
            "selection_reason": mode_report["selection_reason"],
            "modes": mode_report["modes"],
            "deltas_vs_dense": mode_report["deltas_vs_dense"],
        }

    best_real_backend = _find_best_real_backend(rows)
    best_real_mode = rows[best_real_backend]["selected_mode"] if best_real_backend else None
    real_backend_requirement = _build_real_backend_requirement(rows)
    miss_buckets = (
        _build_miss_buckets(cases, rows, best_real_backend, top_k, retriever_factory, modes)
        if best_real_backend is not None
        else []
    )

    return {
        "case_count": len(cases),
        "top_k": top_k,
        "requested_backends": requested_backends,
        "modes": [str(m) for m in modes],
        "real_backend_policy": real_backend_policy,
        "evaluated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "rows": rows,
        "best_real_backend": best_real_backend,
        "best_real_mode": best_real_mode,
        "real_backend_requirement": real_backend_requirement,
        "miss_buckets": miss_buckets,
    }


def _find_best_real_backend(rows: dict[str, dict[str, Any]]) -> str | None:
    best: str | None = None
    best_ndcg: float = -1.0
    for backend, row in rows.items():
        if backend == "hash":
            continue
        if row.get("status") != "measured":
            continue
        selected_mode = row["selected_mode"]
        modes_data = row.get("modes", {})
        mode_entry = modes_data.get(selected_mode, {})
        gm = mode_entry.get("global_metrics", {})
        ndcg = gm.get("ndcg_at_5", 0.0)
        if ndcg > best_ndcg:
            best_ndcg = ndcg
            best = backend
    return best


def _build_real_backend_requirement(
    rows: dict[str, dict[str, Any]],
    *,
    required_backend: str = "bge_small",
) -> dict[str, Any]:
    measured_real = [
        backend
        for backend, row in rows.items()
        if backend != "hash"
        and row.get("status") == "measured"
        and row.get("effective_backend") == backend
    ]
    unavailable_real = [
        backend
        for backend, row in rows.items()
        if backend != "hash" and row.get("status") == "unavailable"
    ]
    not_run_real = [
        backend
        for backend, row in rows.items()
        if backend != "hash" and row.get("status") == "not_run"
    ]
    required_row = rows.get(required_backend, {})
    satisfied = (
        required_row.get("status") == "measured"
        and required_row.get("effective_backend") == required_backend
    )
    reason = (
        f"{required_backend} measured with trusted effective backend"
        if satisfied
        else f"{required_backend} is not a trusted measured backend"
    )
    return {
        "required_backend": required_backend,
        "satisfied": satisfied,
        "measured_real_backends": measured_real,
        "unavailable_real_backends": unavailable_real,
        "not_run_real_backends": not_run_real,
        "reason": reason,
    }


def _build_miss_buckets(
    cases: list[EvalCase],
    rows: dict[str, dict[str, Any]],
    best_real_backend: str,
    top_k: int,
    retriever_factory: Callable[[str], Any] | None,
    modes: list[RagEvalMode],
) -> list[dict[str, Any]]:
    row = rows[best_real_backend]
    selected_mode: str = row["selected_mode"]
    effective_backend: str = row["effective_backend"]

    _R, _S = _get_retriever_classes()

    retriever: Any = (
        retriever_factory(effective_backend)
        if retriever_factory is not None
        else _R(store=_S(embedding_backend=effective_backend))
    )

    report = evaluate_eval_set(
        cases,
        retriever=retriever,
        top_k=top_k,
        embedding_backend=effective_backend,
        mode=selected_mode,  # type: ignore[arg-type]
    )

    results: list[EvalCaseResult] = [EvalCaseResult(**r) for r in report["results"]]
    groups: dict[tuple[str, str], list[EvalCaseResult]] = {}
    for r in results:
        key = (r.scenario_type, r.error_type)
        groups.setdefault(key, []).append(r)

    buckets: list[dict[str, Any]] = []
    for (scenario_type, error_type), group in sorted(groups.items()):
        case_count = len(group)
        miss_count = sum(1 for r in group if r.recall_at_5 < 1.0)
        miss_case_entries = [
            {
                "id": r.id,
                "query": r.query,
                "expected_chunk_ids": r.expected_chunk_ids,
                "retrieved_chunk_ids": r.retrieved_chunk_ids,
                "hit_at_1": r.hit_at_1,
                "recall_at_5": r.recall_at_5,
            }
            for r in group
            if r.recall_at_5 < 1.0
        ]
        buckets.append(
            {
                "scenario_type": scenario_type,
                "error_type": error_type,
                "case_count": case_count,
                "miss_count": miss_count,
                "hit_at_1": sum(r.hit_at_1 for r in group) / case_count,
                "recall_at_5": sum(r.recall_at_5 for r in group) / case_count,
                "mrr": sum(r.reciprocal_rank for r in group) / case_count,
                "ndcg_at_5": sum(r.ndcg_at_5 for r in group) / case_count,
                "miss_cases": miss_case_entries[:5],
            }
        )
    return buckets


def write_matrix_markdown(
    report: dict[str, Any],
    output_path: Path = DEFAULT_MATRIX_REPORT_PATH,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_format_matrix_markdown(report), encoding="utf-8")


def write_matrix_json(
    report: dict[str, Any],
    output_path: Path = DEFAULT_MATRIX_JSON_PATH,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _format_matrix_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# RAG Quality Matrix Report",
        "",
        "## Metadata",
        "",
        "| Key | Value |",
        "|---|---|",
        f"| Case Count | {report['case_count']} |",
        f"| Top K | {report.get('top_k', 5)} |",
        f"| Real Backend Policy | `{report.get('real_backend_policy', 'skip')}` |",
        f"| Evaluated At | {report.get('evaluated_at', 'N/A')} |",
        f"| Best Real Backend | `{report.get('best_real_backend') or 'N/A'}` |",
        f"| Best Real Mode | `{report.get('best_real_mode') or 'N/A'}` |",
        "",
        "## Real Backend Requirement",
        "",
    ]

    req = report.get("real_backend_requirement", {})
    if req:
        satisfied_label = "Yes" if req.get("satisfied") else "No"
        measured = ", ".join(f"`{b}`" for b in req.get("measured_real_backends", [])) or "-"
        unavailable = ", ".join(f"`{b}`" for b in req.get("unavailable_real_backends", [])) or "-"
        not_run = ", ".join(f"`{b}`" for b in req.get("not_run_real_backends", [])) or "-"
        lines.extend([
            "| Key | Value |",
            "|---|---|",
            f"| Required Backend | `{req.get('required_backend', 'N/A')}` |",
            f"| Satisfied | {satisfied_label} |",
            f"| Measured Real Backends | {measured} |",
            f"| Unavailable Real Backends | {unavailable} |",
            f"| Not Run Real Backends | {not_run} |",
            f"| Reason | {req.get('reason', 'N/A')} |",
            "",
        ])
    else:
        lines.extend([
            "No real backend requirement information.",
            "",
        ])

    lines.extend([
        "## Row Summary",
        "",
        "| Backend | Eff Backend | Status | Selected Mode | Reason |",
        "| --- | --- | --- | --- | --- |",
    ])
    rows = report.get("rows", {})
    for backend in report.get("requested_backends", rows.keys()):
        row = rows.get(backend, {})
        status = row.get("status", "N/A")
        eff = row.get("effective_backend") or "-"
        sel_mode = row.get("selected_mode") or "-"
        reason = (row.get("selection_reason") or row.get("reason") or "")[:60]
        lines.append(
            f"| {backend} | {eff} | {status} | {sel_mode} | {reason} |"
        )
    lines.append("")

    lines.extend([
        "## Global Metrics by Backend × Mode",
        "",
    ])
    modes_list: list[str] = report.get("modes", [])
    for mode_name in modes_list:
        header = (
            f"### {mode_name}"
            + " | Backend | Hit@1 | Recall@5 | MRR | NDCG@5 |"
            + "\n| --- | ---: | ---: | ---: | ---: |"
        )
        lines.append(header)
        for backend in report.get("requested_backends", rows.keys()):
            row = rows.get(backend, {})
            if row.get("status") != "measured":
                lines.append(f"| {backend} | - | - | - | - |")
                continue
            mode_data = row.get("modes", {}).get(mode_name, {})
            gm = mode_data.get("global_metrics", {})
            lines.append(
                f"| {backend} | {gm.get('hit_at_1', 0):.4f} | "
                f"{gm.get('recall_at_5', 0):.4f} | "
                f"{gm.get('mrr', 0):.4f} | "
                f"{gm.get('ndcg_at_5', 0):.4f} |"
            )
        lines.append("")

    rows = report.get("rows", {})
    deltas = report.get("deltas_vs_dense", {})
    if deltas or any(
        row.get("deltas_vs_dense") for row in rows.values() if row.get("status") == "measured"
    ):
        lines.extend([
            "## Deltas vs Dense",
            "",
        ])
        for backend in report.get("requested_backends", rows.keys()):
            row = rows.get(backend, {})
            if row.get("status") != "measured" or not row.get("deltas_vs_dense"):
                continue
            lines.append(f"### {backend}")
            lines.append(
                "| Mode | Δ Hit@1 | Δ MRR | Δ NDCG@5 |\n"
                "| --- | ---: | ---: | ---: |"
            )
            for mode_name in sorted(row["deltas_vs_dense"]):
                d = row["deltas_vs_dense"][mode_name]
                sign_h = "+" if d.get("hit_at_1", 0) > 0 else ""
                sign_m = "+" if d.get("mrr", 0) > 0 else ""
                sign_n = "+" if d.get("ndcg_at_5", 0) > 0 else ""
                lines.append(
                    f"| {mode_name} | {sign_h}{d.get('hit_at_1', 0):.4f} | "
                    f"{sign_m}{d.get('mrr', 0):.4f} | {sign_n}{d.get('ndcg_at_5', 0):.4f} |"
                )
            lines.append("")

    miss = report.get("miss_buckets", [])
    if miss:
        lines.extend([
            "## Miss Buckets",
            "",
            f"Best real backend: `{report.get('best_real_backend', 'N/A')}`",
            "",
            "| Scenario | Error Type | Cases | Misses | Hit@1 | Recall@5 | MRR | NDCG@5 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ])
        for bucket in miss:
            lines.append(
                f"| {bucket['scenario_type']} | {bucket['error_type']} | "
                f"{bucket['case_count']} | {bucket['miss_count']} | "
                f"{bucket['hit_at_1']:.4f} | {bucket['recall_at_5']:.4f} | "
                f"{bucket['mrr']:.4f} | {bucket['ndcg_at_5']:.4f} |"
            )
        lines.append("")

        miss_samples_heading_added = False
        for bucket in miss:
            miss_cases = bucket.get("miss_cases", [])
            if not miss_cases:
                continue
            if not miss_samples_heading_added:
                lines.extend([
                    "### Miss Samples",
                    "",
                ])
                miss_samples_heading_added = True
            lines.append(
                f"#### {bucket['scenario_type']} / {bucket['error_type']}"
            )
            lines.append("")
            lines.append(
                "| ID | Query | Expected Chunks | Retrieved Chunks | Hit@1 | Recall@5 |\n"
                "| --- | --- | --- | --- | ---: | ---: |"
            )
            for mc in miss_cases:
                expected = ", ".join(mc["expected_chunk_ids"])
                retrieved = ", ".join(mc["retrieved_chunk_ids"])
                lines.append(
                    f"| {mc['id']} | {mc['query']} | {expected} | {retrieved} | "
                    f"{mc['hit_at_1']:.4f} | {mc['recall_at_5']:.4f} |"
                )
            lines.append("")

    return "\n".join(lines)


def write_mode_comparison_markdown(
    report: dict[str, Any],
    output_path: Path = DEFAULT_COMPARISON_REPORT_PATH,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_format_mode_comparison_markdown(report), encoding="utf-8")


def write_mode_comparison_json(
    report: dict[str, Any],
    output_path: Path = DEFAULT_COMPARISON_JSON_PATH,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _format_mode_comparison_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# RAG Mode Comparison Report",
        "",
        "## Metadata",
        "",
        "| Key | Value |",
        "|---|---|",
        f"| Embedding Backend | `{report.get('embedding_backend', 'unknown')}` |",
        f"| Top K | {report.get('top_k', 5)} |",
        f"| Case Count | {report['case_count']} |",
        f"| Evaluated At | {report.get('evaluated_at', 'N/A')} |",
        "",
        "## Mode Selection",
        "",
        f"- **Baseline**: {report.get('baseline_mode', 'dense')}",
        f"- **Selected**: {report.get('selected_mode', 'dense')}",
        f"- **Reason**: {report.get('selection_reason', 'N/A')}",
        "",
        "## Global Metrics by Mode",
        "",
        "| Mode | Hit@1 | Recall@5 | MRR | NDCG@5 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    modes_data = report.get("modes", {})
    for mode_name in sorted(modes_data):
        gm = modes_data[mode_name].get("global_metrics", {})
        lines.append(
            f"| {mode_name} | {gm.get('hit_at_1', 0):.4f} | {gm.get('recall_at_5', 0):.4f} | "
            f"{gm.get('mrr', 0):.4f} | {gm.get('ndcg_at_5', 0):.4f} |"
        )
    lines.append("")

    deltas = report.get("deltas_vs_dense", {})
    if deltas:
        lines.extend([
            "## Deltas vs Dense",
            "",
            "| Mode | Δ Hit@1 | Δ MRR | Δ NDCG@5 |",
            "| --- | ---: | ---: | ---: |",
        ])
        for mode_name in sorted(deltas):
            d = deltas[mode_name]
            sign_h = "+" if d.get("hit_at_1", 0) > 0 else ""
            sign_m = "+" if d.get("mrr", 0) > 0 else ""
            sign_n = "+" if d.get("ndcg_at_5", 0) > 0 else ""
            lines.append(
                f"| {mode_name} | {sign_h}{d.get('hit_at_1', 0):.4f} | "
                f"{sign_m}{d.get('mrr', 0):.4f} | {sign_n}{d.get('ndcg_at_5', 0):.4f} |"
            )
        lines.append("")

    return "\n".join(lines)


def _matrix_row_for_backend(matrix: dict[str, Any], backend: str) -> dict[str, Any]:
    return matrix.get("rows", {}).get(backend, {})


def _global_metrics_for_mode(matrix: dict[str, Any], backend: str, mode: str) -> dict[str, float]:
    row = _matrix_row_for_backend(matrix, backend)
    return row.get("modes", {}).get(mode, {}).get("global_metrics", {})


def _bucket_metrics_for_mode(
    matrix: dict[str, Any],
    backend: str,
    mode: str,
    *,
    source_label: str = "",
) -> tuple[list[dict[str, Any]], str | None, str | None]:
    row = _matrix_row_for_backend(matrix, backend)
    mode_entry = row.get("modes", {}).get(mode, {})
    bucket_metrics = mode_entry.get("bucket_metrics")
    if bucket_metrics:
        return list(bucket_metrics), "mode_bucket_metrics", None

    if matrix.get("best_real_backend") == backend and matrix.get("best_real_mode") == mode:
        legacy_buckets = matrix.get("miss_buckets", [])
        if legacy_buckets:
            return list(legacy_buckets), "legacy_top_level_miss_buckets", None

    return [], None, f"{source_label} matrix lacks bucket_metrics for {backend}/{mode}"


def _bucket_by_key(matrix: dict[str, Any], backend: str, mode: str, scenario_type: str, error_type: str) -> dict[str, Any]:
    for bucket in _bucket_metrics_for_mode(matrix, backend, mode)[0]:
        if bucket.get("scenario_type") == scenario_type and bucket.get("error_type") == error_type:
            return bucket
    return {}


def _metric_delta(after: dict[str, Any], before: dict[str, Any]) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    for key in ["miss_count", "hit_at_1", "recall_at_5", "mrr", "ndcg_at_5"]:
        if key in after and key in before:
            delta[key] = after[key] - before[key]
    return delta


def _bucket_deltas(baseline_matrix: dict[str, Any], after_matrix: dict[str, Any], backend: str, mode: str) -> list[dict[str, Any]]:
    baseline_buckets = _bucket_metrics_for_mode(baseline_matrix, backend, mode)[0]
    after_buckets = _bucket_metrics_for_mode(after_matrix, backend, mode)[0]
    after_by_key: dict[tuple[str, str], dict[str, Any]] = {
        (b["scenario_type"], b["error_type"]): b for b in after_buckets
    }

    deltas: list[dict[str, Any]] = []
    for baseline_bucket in baseline_buckets:
        key = (baseline_bucket["scenario_type"], baseline_bucket["error_type"])
        after_bucket = after_by_key.get(key)
        if after_bucket is None:
            continue
        delta = _metric_delta(after_bucket, baseline_bucket)
        deltas.append(
            {
                "scenario_type": baseline_bucket["scenario_type"],
                "error_type": baseline_bucket["error_type"],
                "before": {
                    "case_count": baseline_bucket["case_count"],
                    "miss_count": baseline_bucket["miss_count"],
                    "hit_at_1": baseline_bucket["hit_at_1"],
                    "recall_at_5": baseline_bucket["recall_at_5"],
                    "mrr": baseline_bucket["mrr"],
                    "ndcg_at_5": baseline_bucket["ndcg_at_5"],
                },
                "after": {
                    "case_count": after_bucket["case_count"],
                    "miss_count": after_bucket["miss_count"],
                    "hit_at_1": after_bucket["hit_at_1"],
                    "recall_at_5": after_bucket["recall_at_5"],
                    "mrr": after_bucket["mrr"],
                    "ndcg_at_5": after_bucket["ndcg_at_5"],
                },
                "delta": delta,
            }
        )
    return deltas


def build_optimization_comparison_report(
    baseline_matrix: dict[str, Any],
    after_matrix: dict[str, Any],
    *,
    target_scenario_type: str = "BANK_CLEARING",
    target_error_type: str = "SINGLE_SIDE_MISSING",
    backend: str = "bge_m3",
    mode: str = "hybrid",
    max_global_regression: float = 0.0200,
) -> dict[str, Any]:
    baseline_row = _matrix_row_for_backend(baseline_matrix, backend)
    after_row = _matrix_row_for_backend(after_matrix, backend)

    baseline_source = {
        "case_count": baseline_matrix.get("case_count"),
        "top_k": baseline_matrix.get("top_k"),
        "real_backend_policy": baseline_matrix.get("real_backend_policy"),
        "requested_backend": backend,
        "effective_backend": baseline_row.get("effective_backend"),
        "status": baseline_row.get("status"),
        "mode": mode,
    }
    after_source = {
        "case_count": after_matrix.get("case_count"),
        "top_k": after_matrix.get("top_k"),
        "real_backend_policy": after_matrix.get("real_backend_policy"),
        "requested_backend": backend,
        "effective_backend": after_row.get("effective_backend"),
        "status": after_row.get("status"),
        "mode": mode,
    }

    trust_reasons: list[str] = []
    trusted = True
    if baseline_source["status"] != "measured" or baseline_source["effective_backend"] != backend:
        trust_reasons.append(f"baseline backend {backend} is not trusted (status={baseline_source['status']}, effective={baseline_source['effective_backend']})")
        trusted = False
    if after_source["status"] != "measured" or after_source["effective_backend"] != backend:
        trust_reasons.append(f"after backend {backend} is not trusted (status={after_source['status']}, effective={after_source['effective_backend']})")
        trusted = False
    if baseline_source["case_count"] != after_source["case_count"]:
        trust_reasons.append(f"case_count mismatch: baseline={baseline_source['case_count']}, after={after_source['case_count']}")
        trusted = False
    if baseline_source["top_k"] != after_source["top_k"]:
        trust_reasons.append(f"top_k mismatch: baseline={baseline_source['top_k']}, after={after_source['top_k']}")
        trusted = False

    baseline_buckets, baseline_bucket_source, baseline_bucket_err = _bucket_metrics_for_mode(
        baseline_matrix, backend, mode, source_label="baseline"
    )
    after_buckets, after_bucket_source, after_bucket_err = _bucket_metrics_for_mode(
        after_matrix, backend, mode, source_label="after"
    )
    if baseline_bucket_err:
        trust_reasons.append(baseline_bucket_err)
        trusted = False
    if after_bucket_err:
        trust_reasons.append(after_bucket_err)
        trusted = False

    baseline_global = _global_metrics_for_mode(baseline_matrix, backend, mode)
    after_global = _global_metrics_for_mode(after_matrix, backend, mode)
    if not baseline_global:
        trust_reasons.append(f"baseline matrix lacks global_metrics for {backend}/{mode}")
        trusted = False
    if not after_global:
        trust_reasons.append(f"after matrix lacks global_metrics for {backend}/{mode}")
        trusted = False

    trust = {
        "trusted": trusted,
        "reasons": trust_reasons,
        "bucket_metric_sources": {
            "baseline": baseline_bucket_source or "missing",
            "after": after_bucket_source or "missing",
        },
    }

    target_before = _bucket_by_key(baseline_matrix, backend, mode, target_scenario_type, target_error_type)
    target_after = _bucket_by_key(after_matrix, backend, mode, target_scenario_type, target_error_type)

    if target_before and target_after:
        target_delta = _metric_delta(target_after, target_before)
        target_improved = (
            target_after.get("recall_at_5", 0) > target_before.get("recall_at_5", 0)
            and target_after.get("miss_count", 0) < target_before.get("miss_count", 0)
        )
    else:
        target_delta = {}
        target_improved = False

    target_bucket = {
        "before": {
            "case_count": target_before.get("case_count"),
            "miss_count": target_before.get("miss_count"),
            "hit_at_1": target_before.get("hit_at_1"),
            "recall_at_5": target_before.get("recall_at_5"),
            "mrr": target_before.get("mrr"),
            "ndcg_at_5": target_before.get("ndcg_at_5"),
        } if target_before else {},
        "after": {
            "case_count": target_after.get("case_count"),
            "miss_count": target_after.get("miss_count"),
            "hit_at_1": target_after.get("hit_at_1"),
            "recall_at_5": target_after.get("recall_at_5"),
            "mrr": target_after.get("mrr"),
            "ndcg_at_5": target_after.get("ndcg_at_5"),
        } if target_after else {},
        "delta": target_delta,
        "improved": target_improved,
    }

    if baseline_global and after_global:
        global_delta = _metric_delta(after_global, baseline_global)
        within_regression_limit = True
        if "mrr" in global_delta and global_delta["mrr"] < -max_global_regression:
            within_regression_limit = False
        if "ndcg_at_5" in global_delta and global_delta["ndcg_at_5"] < -max_global_regression:
            within_regression_limit = False
    else:
        global_delta = {}
        within_regression_limit = False

    global_section = {
        "before": {
            "hit_at_1": baseline_global.get("hit_at_1"),
            "recall_at_5": baseline_global.get("recall_at_5"),
            "mrr": baseline_global.get("mrr"),
            "ndcg_at_5": baseline_global.get("ndcg_at_5"),
        } if baseline_global else {},
        "after": {
            "hit_at_1": after_global.get("hit_at_1"),
            "recall_at_5": after_global.get("recall_at_5"),
            "mrr": after_global.get("mrr"),
            "ndcg_at_5": after_global.get("ndcg_at_5"),
        } if after_global else {},
        "delta": global_delta,
        "within_regression_limit": within_regression_limit,
        "max_global_regression": max_global_regression,
    }

    all_deltas = _bucket_deltas(baseline_matrix, after_matrix, backend, mode)
    non_target_deltas = [
        d for d in all_deltas
        if not (d["scenario_type"] == target_scenario_type and d["error_type"] == target_error_type)
    ]

    regressions = [d for d in non_target_deltas if d["delta"].get("ndcg_at_5", 0) < 0]
    regressions.sort(key=lambda d: (d["delta"]["ndcg_at_5"], d["scenario_type"], d["error_type"]))
    improvements = [d for d in non_target_deltas if d["delta"].get("ndcg_at_5", 0) > 0]
    improvements.sort(key=lambda d: (-d["delta"]["ndcg_at_5"], d["scenario_type"], d["error_type"]))

    side_effect_buckets = {
        "largest_regressions": regressions[:3],
        "largest_improvements": improvements[:3],
    }

    failure_reasons: list[str] = []
    success = True

    if not trust["trusted"]:
        failure_reasons.extend(trust_reasons)
        success = False

    if not target_improved:
        failure_reasons.append(
            f"target bucket {target_scenario_type}/{target_error_type} did not improve "
            f"(recall: {target_before.get('recall_at_5')} -> {target_after.get('recall_at_5')}, "
            f"miss_count: {target_before.get('miss_count')} -> {target_after.get('miss_count')})"
        )
        success = False

    if not within_regression_limit:
        failure_reasons.append(
            f"global metrics regressed beyond {max_global_regression} "
            f"(mrr delta: {global_delta.get('mrr')}, ndcg_at_5 delta: {global_delta.get('ndcg_at_5')})"
        )
        success = False

    return {
        "target": {
            "scenario_type": target_scenario_type,
            "error_type": target_error_type,
            "backend": backend,
            "mode": mode,
        },
        "baseline_source": baseline_source,
        "after_source": after_source,
        "trust": trust,
        "target_bucket": target_bucket,
        "global": global_section,
        "side_effect_buckets": side_effect_buckets,
        "success": success,
        "failure_reasons": failure_reasons,
    }


def write_optimization_comparison_markdown(
    report: dict[str, Any],
    output_path: Path = DEFAULT_OPTIMIZATION_COMPARISON_REPORT_PATH,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_format_optimization_comparison_markdown(report), encoding="utf-8")


def write_optimization_comparison_json(
    report: dict[str, Any],
    output_path: Path = DEFAULT_OPTIMIZATION_COMPARISON_JSON_PATH,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _format_optimization_comparison_markdown(report: dict[str, Any]) -> str:
    target = report["target"]
    lines = [
        "# RAG Optimization Comparison Report",
        "",
        "## Target",
        "",
        f"- **Scenario**: {target['scenario_type']}",
        f"- **Error Type**: {target['error_type']}",
        f"- **Backend**: `{target['backend']}`",
        f"- **Mode**: `{target['mode']}`",
        "",
        "## Trust",
        "",
    ]

    trust = report["trust"]
    trusted_label = "Yes" if trust["trusted"] else "No"
    lines.append(f"- **Trusted**: {trusted_label}")
    for reason in trust.get("reasons", []):
        lines.append(f"  - {reason}")
    lines.append("")

    baseline = report["baseline_source"]
    after = report["after_source"]
    lines.extend([
        "## Baseline Source",
        "",
        f"- case_count: {baseline.get('case_count')}",
        f"- top_k: {baseline.get('top_k')}",
        f"- status: {baseline.get('status')}",
        f"- effective_backend: `{baseline.get('effective_backend')}`",
        f"- real_backend_policy: {baseline.get('real_backend_policy')}",
        "",
        "## After Source",
        "",
        f"- case_count: {after.get('case_count')}",
        f"- top_k: {after.get('top_k')}",
        f"- status: {after.get('status')}",
        f"- effective_backend: `{after.get('effective_backend')}`",
        f"- real_backend_policy: {after.get('real_backend_policy')}",
        "",
        "## Target Bucket",
        "",
        "| Metric | Before | After | Delta |",
        "| --- | ---: | ---: | ---: |",
    ])

    tb = report["target_bucket"]
    for metric in ["miss_count", "hit_at_1", "recall_at_5", "mrr", "ndcg_at_5"]:
        b_val = tb["before"].get(metric, "-")
        a_val = tb["after"].get(metric, "-")
        d_val = tb["delta"].get(metric, "-")
        if isinstance(b_val, float):
            b_val = f"{b_val:.4f}"
            a_val = f"{a_val:.4f}" if isinstance(a_val, float) else a_val
            d_val = f"{d_val:.4f}" if isinstance(d_val, float) else d_val
        lines.append(f"| {metric} | {b_val} | {a_val} | {d_val} |")

    lines.extend([
        "",
        f"- **Improved**: {'Yes' if tb.get('improved') else 'No'}",
        "",
        "## Global",
        "",
        "| Metric | Before | After | Delta |",
        "| --- | ---: | ---: | ---: |",
    ])

    g = report["global"]
    for metric in ["hit_at_1", "recall_at_5", "mrr", "ndcg_at_5"]:
        b_val = g["before"].get(metric, "-")
        a_val = g["after"].get(metric, "-")
        d_val = g["delta"].get(metric, "-")
        if isinstance(b_val, float):
            b_val = f"{b_val:.4f}"
            a_val = f"{a_val:.4f}"
            d_val = f"{d_val:.4f}"
        lines.append(f"| {metric} | {b_val} | {a_val} | {d_val} |")

    lines.extend([
        "",
        f"- **Within Regression Limit**: {'Yes' if g.get('within_regression_limit') else 'No'}",
        f"- **Max Allowed Regression**: {g.get('max_global_regression', '+0.0200')}",
        "",
    ])

    se = report["side_effect_buckets"]
    regressions = se.get("largest_regressions", [])
    if regressions:
        lines.extend([
            "## Largest Regressions (up to 3)",
            "",
            "| Scenario | Error Type | Δ NDCG@5 | Δ MRR | Δ Recall@5 |",
            "| --- | --- | ---: | ---: | ---: |",
        ])
        for r in regressions:
            d = r["delta"]
            lines.append(
                f"| {r['scenario_type']} | {r['error_type']} | "
                f"{d.get('ndcg_at_5', 0):.4f} | {d.get('mrr', 0):.4f} | {d.get('recall_at_5', 0):.4f} |"
            )
        lines.append("")

    improvements = se.get("largest_improvements", [])
    if improvements:
        lines.extend([
            "## Largest Improvements (up to 3)",
            "",
            "| Scenario | Error Type | Δ NDCG@5 | Δ MRR | Δ Recall@5 |",
            "| --- | --- | ---: | ---: | ---: |",
        ])
        for r in improvements:
            d = r["delta"]
            lines.append(
                f"| {r['scenario_type']} | {r['error_type']} | "
                f"{d.get('ndcg_at_5', 0):.4f} | {d.get('mrr', 0):.4f} | {d.get('recall_at_5', 0):.4f} |"
            )
        lines.append("")

    success_label = "Yes" if report["success"] else "No"
    lines.extend([
        "## Verdict",
        "",
        f"- **Success**: {success_label}",
    ])
    failure_reasons = report.get("failure_reasons", [])
    if failure_reasons:
        lines.append("- **Failure Reasons**:")
        for reason in failure_reasons:
            lines.append(f"  - {reason}")
    lines.append("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Evaluate offline RAG quality with a labeled eval set.")
    parser.add_argument("--eval-set", type=Path, default=DEFAULT_EVAL_SET_PATH)
    parser.add_argument("--chunks", type=Path, default=None)
    parser.add_argument("--chroma", type=Path, default=None)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--json-report", type=Path, default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--embedding-backend", default=settings.embedding_backend)
    parser.add_argument("--mode", choices=["dense", "hybrid", "hybrid_rerank"], default="dense")
    parser.add_argument("--compare-modes", type=str, default=None)
    parser.add_argument("--comparison-report", type=Path, default=DEFAULT_COMPARISON_REPORT_PATH)
    parser.add_argument("--comparison-json", type=Path, default=DEFAULT_COMPARISON_JSON_PATH)
    parser.add_argument("--matrix-backends", type=str, default=None)
    parser.add_argument("--matrix-modes", type=str, default=None)
    parser.add_argument("--real-backend-policy", choices=["skip", "auto"], default="skip")
    parser.add_argument("--matrix-report", type=Path, default=DEFAULT_MATRIX_REPORT_PATH)
    parser.add_argument("--matrix-json", type=Path, default=DEFAULT_MATRIX_JSON_PATH)
    parser.add_argument("--optimization-baseline-json", type=Path, default=None)
    parser.add_argument("--optimization-after-json", type=Path, default=None)
    parser.add_argument("--optimization-report", type=Path, default=DEFAULT_OPTIMIZATION_COMPARISON_REPORT_PATH)
    parser.add_argument("--optimization-json", type=Path, default=DEFAULT_OPTIMIZATION_COMPARISON_JSON_PATH)
    parser.add_argument("--optimization-target-scenario", default="BANK_CLEARING")
    parser.add_argument("--optimization-target-error-type", default="SINGLE_SIDE_MISSING")
    parser.add_argument("--optimization-backend", default="bge_m3")
    parser.add_argument("--optimization-mode", default="hybrid")
    args = parser.parse_args(argv)

    has_baseline = args.optimization_baseline_json is not None
    has_after = args.optimization_after_json is not None
    if has_baseline != has_after:
        parser.error("--optimization-baseline-json and --optimization-after-json must both be provided, or neither")

    if has_baseline and has_after:
        baseline_matrix = json.loads(args.optimization_baseline_json.read_text(encoding="utf-8"))
        after_matrix = json.loads(args.optimization_after_json.read_text(encoding="utf-8"))
        comparison = build_optimization_comparison_report(
            baseline_matrix,
            after_matrix,
            target_scenario_type=args.optimization_target_scenario,
            target_error_type=args.optimization_target_error_type,
            backend=args.optimization_backend,
            mode=args.optimization_mode,
        )
        if args.optimization_report:
            write_optimization_comparison_markdown(comparison, args.optimization_report)
        if args.optimization_json:
            write_optimization_comparison_json(comparison, args.optimization_json)
        print(json.dumps(comparison, ensure_ascii=False, indent=2))
        return

    if args.chunks is not None:
        dense_summary = evaluate_cases(
            chunks_path=args.chunks,
            chroma_path=(args.chroma or PROJECT_ROOT / "chroma_eval") / "dense",
            mode="dense",
            embedding_backend=args.embedding_backend,
        )
        hybrid_summary = evaluate_cases(
            chunks_path=args.chunks,
            chroma_path=(args.chroma or PROJECT_ROOT / "chroma_eval") / "hybrid_rerank",
            mode="hybrid_rerank",
            embedding_backend=args.embedding_backend,
        )
        _print_legacy_report(dense_summary, hybrid_summary)
        return

    if args.matrix_backends is not None:
        matrix_backends: list[str] = [
            b.strip() for b in args.matrix_backends.split(",")
        ]
        matrix_modes: list[RagEvalMode] = [
            m.strip() for m in (args.matrix_modes or "dense,hybrid,hybrid_rerank").split(",")  # type: ignore[assignment]
        ]
        matrix_report = evaluate_backend_mode_matrix(
            load_eval_set(args.eval_set),
            requested_backends=matrix_backends,
            modes=matrix_modes,
            top_k=args.top_k,
            real_backend_policy=args.real_backend_policy,
        )
        if args.matrix_report:
            write_matrix_markdown(matrix_report, args.matrix_report)
        if args.matrix_json:
            write_matrix_json(matrix_report, args.matrix_json)
        print(json.dumps(matrix_report, ensure_ascii=False, indent=2))
        return

    retriever: Any
    if args.chroma is None and args.embedding_backend == settings.embedding_backend:
        retriever = _get_rule_retriever()
    else:
        _R, _S = _get_retriever_classes()
        retriever = _R(
            store=_S(
                chroma_path=args.chroma,
                embedding_backend=args.embedding_backend,
            )
        )

    if args.compare_modes is not None:
        modes: list[RagEvalMode] = [
            m.strip() for m in args.compare_modes.split(",")  # type: ignore[assignment]
        ]
        report = evaluate_mode_comparison(
            load_eval_set(args.eval_set),
            retriever=retriever,
            modes=modes,
            top_k=args.top_k,
            embedding_backend=args.embedding_backend,
        )
        if args.comparison_report:
            write_mode_comparison_markdown(report, args.comparison_report)
        if args.comparison_json:
            write_mode_comparison_json(report, args.comparison_json)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    report = evaluate_eval_set(
        load_eval_set(args.eval_set),
        retriever=retriever,
        top_k=args.top_k,
        embedding_backend=args.embedding_backend,
        mode=args.mode,
    )
    write_markdown_report(report, args.report)
    write_json_metrics_snapshot(report, args.json_report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def write_markdown_report(report: dict[str, Any], output_path: Path = DEFAULT_REPORT_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_format_markdown_report(report), encoding="utf-8")


def write_json_metrics_snapshot(
    report: dict[str, Any],
    output_path: Path = DEFAULT_JSON_REPORT_PATH,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_to_metrics_snapshot(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _to_metrics_snapshot(report: dict[str, Any]) -> dict[str, object]:
    global_metrics = report.get("global_metrics", {})
    summaries = report["summaries"]
    total_cases = sum(summary["case_count"] for summary in summaries)
    recall_at5 = global_metrics.get(
        "recall_at_5", _weighted_average(summaries, "recall_at_5", total_cases),
    )
    mrr = global_metrics.get(
        "mrr", _weighted_average(summaries, "mrr", total_cases),
    )
    evaluated_at = report.get(
        "evaluated_at",
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    snapshot: dict[str, object] = {
        # Backward-compatible required keys
        "rag_recall_at5": recall_at5,
        "rag_mrr": mrr,
        "evaluated_at": evaluated_at,
        # Richer keys
        "rag_hit_at1": global_metrics.get(
            "hit_at_1", _weighted_average(summaries, "hit_at_1", total_cases),
        ),
        "rag_ndcg_at5": global_metrics.get(
            "ndcg_at_5", _weighted_average(summaries, "ndcg_at_5", total_cases),
        ),
        "embedding_backend": report.get("embedding_backend", "unknown"),
        "top_k": report.get("top_k", 5),
        "case_count": report.get("case_count", total_cases),
    }
    return snapshot


def _weighted_average(summaries: list[dict[str, Any]], metric: str, total_cases: int) -> float:
    if total_cases == 0:
        return 0.0
    return sum(summary[metric] * summary["case_count"] for summary in summaries) / total_cases


def _compute_global_metrics(
    summaries: list[ScenarioSummary | dict[str, Any]],
    total_cases: int,
) -> dict[str, float]:
    """Compute weighted global metrics across all scenarios."""
    as_dicts = [
        asdict(s) if not isinstance(s, dict) else s for s in summaries
    ]
    return {
        "hit_at_1": _weighted_average(as_dicts, "hit_at_1", total_cases),
        "recall_at_5": _weighted_average(as_dicts, "recall_at_5", total_cases),
        "mrr": _weighted_average(as_dicts, "mrr", total_cases),
        "ndcg_at_5": _weighted_average(as_dicts, "ndcg_at_5", total_cases),
    }


def _build_saturation_notes(
    global_metrics: dict[str, float],
    summaries: list[ScenarioSummary | dict[str, Any]],
) -> list[str]:
    """Build evaluation notes including Recall@5 saturation risk."""
    notes = [
        "Recall@5 is evaluated on desaturated bank-enterprise and bank-clearing corpora; "
        "use MRR, NDCG@5, and Hit@1 for ranking quality.",
    ]
    if global_metrics.get("recall_at_5", 0) == 1.0:
        notes.append(
            "⚠️ Recall@5 = 1.0 globally. This may indicate top-k saturation: "
            "all expected chunks fall within top-5 results. "
            "Inspect Hit@1, MRR, and NDCG@5 for ranking quality."
        )
    for summary in summaries:
        s = asdict(summary) if not isinstance(summary, dict) else summary
        if s.get("recall_at_5", 0) == 1.0:
            notes.append(
                f"⚠️ Recall@5 = 1.0 for scenario {s['scenario_type']}. "
                f"Possible top-k saturation. Hit@1={s.get('hit_at_1', 'N/A'):.4f}, "
                f"MRR={s.get('mrr', 'N/A'):.4f}."
            )
    return notes


def _summarize_by_error_type(results: list[EvalCaseResult]) -> list[ErrorTypeSummary]:
    """Group results by (scenario_type, error_type) and compute per-group metrics."""
    groups: dict[tuple[str, str], list[EvalCaseResult]] = {}
    for result in results:
        key = (result.scenario_type, result.error_type)
        groups.setdefault(key, []).append(result)

    summaries: list[ErrorTypeSummary] = []
    for (scenario_type, error_type), group_results in sorted(groups.items()):
        case_count = len(group_results)
        summaries.append(ErrorTypeSummary(
            scenario_type=scenario_type,
            error_type=error_type,
            case_count=case_count,
            hit_at_1=sum(r.hit_at_1 for r in group_results) / case_count,
            recall_at_5=sum(r.recall_at_5 for r in group_results) / case_count,
            mrr=sum(r.reciprocal_rank for r in group_results) / case_count,
            ndcg_at_5=sum(r.ndcg_at_5 for r in group_results) / case_count,
        ))
    return summaries


def _format_markdown_report(report: dict[str, Any]) -> str:
    global_metrics = report.get("global_metrics", {})
    lines = [
        "# RAG Evaluation Report",
        "",
        "## Metadata",
        "",
        "| Key | Value |",
        "|---|---|",
        f"| Embedding Backend | `{report.get('embedding_backend', 'unknown')}` |",
        f"| Top K | {report.get('top_k', 5)} |",
        f"| Case Count | {report['case_count']} |",
        f"| Evaluated At | {report.get('evaluated_at', 'N/A')} |",
        "",
        "## Global Metrics",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Hit@1 | {global_metrics.get('hit_at_1', 0):.4f} |",
        f"| Recall@5 | {global_metrics.get('recall_at_5', 0):.4f} |",
        f"| MRR | {global_metrics.get('mrr', 0):.4f} |",
        f"| NDCG@5 | {global_metrics.get('ndcg_at_5', 0):.4f} |",
        "",
        "## By Scenario",
        "",
        "| Scenario | Cases | Hit@1 | Recall@5 | MRR | NDCG@5 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for summary in report["summaries"]:
        lines.append(
            "| {scenario_type} | {case_count} | {hit_at_1:.4f} | {recall_at_5:.4f} | "
            "{mrr:.4f} | {ndcg_at_5:.4f} |".format(**summary)
        )
    lines.append("")

    # Error-type grouping
    error_type_summaries = report.get("error_type_summaries", [])
    if error_type_summaries:
        lines.extend([
            "## By Scenario × Error Type",
            "",
            "| Scenario | Error Type | Cases | Hit@1 | Recall@5 | MRR | NDCG@5 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ])
        for summary in error_type_summaries:
            lines.append(
                "| {scenario_type} | {error_type} | {case_count} | {hit_at_1:.4f} | "
                "{recall_at_5:.4f} | {mrr:.4f} | {ndcg_at_5:.4f} |".format(**summary)
            )
        lines.append("")

    # Notes including saturation
    notes = report.get("notes", [])
    if notes:
        lines.extend(["## Notes", ""])
        for note in notes:
            lines.append(f"- {note}")
        lines.append("")

    return "\n".join(lines)


def _evaluate_case(
    case: EvalCase,
    *,
    retriever: Any,
    top_k: int,
    min_score: float,
    mode: RagEvalMode = "dense",
) -> EvalCaseResult:
    response = retriever.search(
        request_for_eval_mode(case, mode=mode, top_k=top_k, min_score=min_score)
    )
    retrieved_chunk_ids = [item.chunk_id for item in response.items[:top_k]]
    return EvalCaseResult(
        id=case.id,
        scenario_type=case.scenario_type,
        error_type=case.error_type,
        query=case.query,
        expected_chunk_ids=case.expected_chunk_ids,
        retrieved_chunk_ids=retrieved_chunk_ids,
        hit_at_1=_hit_at_1(retrieved_chunk_ids, case.expected_chunk_ids),
        recall_at_5=_recall_at_k(retrieved_chunk_ids, case.expected_chunk_ids, top_k),
        reciprocal_rank=_reciprocal_rank(retrieved_chunk_ids, case.expected_chunk_ids, top_k),
        ndcg_at_5=_ndcg_at_k(retrieved_chunk_ids, case.expected_chunk_ids, top_k),
    )


def _summarize_scenario(results: list[EvalCaseResult], scenario_type: str) -> ScenarioSummary:
    scenario_results = [result for result in results if result.scenario_type == scenario_type]
    case_count = len(scenario_results)
    if case_count == 0:
        return ScenarioSummary(
            scenario_type=scenario_type,
            case_count=0,
            hit_at_1=0.0,
            recall_at_5=0.0,
            mrr=0.0,
            ndcg_at_5=0.0,
        )

    return ScenarioSummary(
        scenario_type=scenario_type,
        case_count=case_count,
        hit_at_1=sum(result.hit_at_1 for result in scenario_results) / case_count,
        recall_at_5=sum(result.recall_at_5 for result in scenario_results) / case_count,
        mrr=sum(result.reciprocal_rank for result in scenario_results) / case_count,
        ndcg_at_5=sum(result.ndcg_at_5 for result in scenario_results) / case_count,
    )


def _hit_at_1(retrieved_chunk_ids: list[str], expected_chunk_ids: list[str]) -> float:
    expected = set(expected_chunk_ids)
    if not expected or not retrieved_chunk_ids:
        return 0.0
    return 1.0 if retrieved_chunk_ids[0] in expected else 0.0


def _recall_at_k(retrieved_chunk_ids: list[str], expected_chunk_ids: list[str], top_k: int) -> float:
    expected = set(expected_chunk_ids)
    if not expected:
        return 0.0
    hits = sum(chunk_id in expected for chunk_id in retrieved_chunk_ids[:top_k])
    return hits / len(expected)


def _reciprocal_rank(retrieved_chunk_ids: list[str], expected_chunk_ids: list[str], top_k: int) -> float:
    expected = set(expected_chunk_ids)
    for index, chunk_id in enumerate(retrieved_chunk_ids[:top_k], start=1):
        if chunk_id in expected:
            return 1.0 / index
    return 0.0


def _ndcg_at_k(retrieved_chunk_ids: list[str], expected_chunk_ids: list[str], top_k: int) -> float:
    expected = set(expected_chunk_ids)
    if not expected:
        return 0.0

    dcg = 0.0
    for index, chunk_id in enumerate(retrieved_chunk_ids[:top_k], start=1):
        if chunk_id in expected:
            dcg += 1.0 / math.log2(index + 1)

    ideal_hits = min(len(expected), top_k)
    idcg = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
    if idcg == 0.0:
        return 0.0
    return dcg / idcg


def evaluate_cases(
    *,
    chunks_path: Path = DEFAULT_CHUNKS_PATH,
    chroma_path: Path = PROJECT_ROOT / "chroma_eval",
    mode: str,
    embedding_backend: str | None = None,
) -> LegacyEvalSummary:
    _R, _S = _get_retriever_classes()
    retriever = _R(
        store=_S(
            chunks_path=chunks_path,
            chroma_path=chroma_path,
            embedding_backend=embedding_backend,
        )
    )
    return LegacyEvalSummary(
        mode=mode,
        case_results=[
            _evaluate_smoke_case(
                retriever,
                case,
                mode=mode,
            )
            for case in SMOKE_CASES
        ],
    )


def _evaluate_smoke_case(
    retriever: Any,
    case: SmokeCase,
    *,
    mode: str,
) -> LegacyCaseResult:
    response = retriever.search(
        _request_for_mode(
            case.query,
            mode=mode,
        )
    )
    matched_item = _find_hit(response.items, expected_tag=case.expected_tag)
    score = representative_score(matched_item) if matched_item is not None else None
    return LegacyCaseResult(
        query=case.query,
        expected_tag=case.expected_tag,
        matched_chunk_id=matched_item.chunk_id if matched_item is not None else None,
        representative_score=score,
        reranker_score=matched_item.reranker_score if matched_item is not None else None,
        hit=matched_item is not None,
    )


def _request_for_mode(
    query: str,
    *,
    mode: str,
) -> RagSearchRequest:
    if mode == "dense":
        return RagSearchRequest(query=query, top_k=settings.rag_rerank_top_k, min_score=0.0)
    if mode == "hybrid_rerank":
        return RagSearchRequest(
            query=query,
            top_k=settings.rag_rerank_top_k,
            min_score=0.0,
            enable_hybrid=True,
            enable_reranker=True,
        )
    raise ValueError(f"unsupported mode: {mode}")


def _find_hit(items: list[RagSearchItem], *, expected_tag: str) -> RagSearchItem | None:
    for item in items:
        if expected_tag in item.business_tags:
            return item
    return None


def _print_legacy_report(dense_summary: LegacyEvalSummary, hybrid_summary: LegacyEvalSummary) -> None:
    print("mode\thit_count\tcase_count\tavg_reranker_score")
    for summary in (dense_summary, hybrid_summary):
        print(
            f"{summary.mode}\t{summary.hit_count}\t{len(summary.case_results)}\t"
            f"{summary.average_reranker_score:.4f}"
        )

    print("")
    print("query\texpected_tag\tdense_hit\thybrid_hit\tdense_chunk\thybrid_chunk")
    for dense_result, hybrid_result in zip(
        dense_summary.case_results,
        hybrid_summary.case_results,
        strict=True,
    ):
        print(
            f"{dense_result.query}\t{dense_result.expected_tag}\t"
            f"{int(dense_result.hit)}\t{int(hybrid_result.hit)}\t"
            f"{dense_result.matched_chunk_id or '-'}\t{hybrid_result.matched_chunk_id or '-'}"
        )


if __name__ == "__main__":
    main()
