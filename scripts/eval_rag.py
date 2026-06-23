from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.rag.retriever import ChromaRuleStore, RuleRetriever, rule_retriever
from bank_reconciliation_agent.rag.scoring import representative_score
from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchRequest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVAL_SET_PATH = PROJECT_ROOT / "data/rag_eval_set.json"
DEFAULT_CHUNKS_PATH = PROJECT_ROOT / "data/rag/rule_chunks_bank_enterprise.jsonl"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "reports/rag_eval.md"
DEFAULT_JSON_REPORT_PATH = PROJECT_ROOT / "reports/rag_eval_metrics.json"


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


def evaluate_eval_set(
    cases: list[EvalCase],
    *,
    retriever: RuleRetriever | Any = rule_retriever,
    top_k: int = 5,
) -> dict[str, Any]:
    results = [_evaluate_case(case, retriever=retriever, top_k=top_k) for case in cases]
    scenario_types = sorted({case.scenario_type for case in cases})
    summaries = [_summarize_scenario(results, scenario_type) for scenario_type in scenario_types]
    return {
        "case_count": len(cases),
        "notes": [
            "Recall@5 is evaluated on desaturated bank-enterprise and bank-clearing corpora; use MRR, NDCG@5, and Hit@1 for ranking quality."
        ],
        "summaries": [asdict(summary) for summary in summaries],
        "results": [asdict(result) for result in results],
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Evaluate offline RAG quality with a labeled eval set.")
    parser.add_argument("--eval-set", type=Path, default=DEFAULT_EVAL_SET_PATH)
    parser.add_argument("--chunks", type=Path, default=None)
    parser.add_argument("--chroma", type=Path, default=None)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--json-report", type=Path, default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--embedding-backend", default=settings.embedding_backend)
    args = parser.parse_args(argv)

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

    retriever = (
        rule_retriever
        if args.chroma is None and args.embedding_backend == settings.embedding_backend
        else RuleRetriever(
            store=ChromaRuleStore(
                chroma_path=args.chroma,
                embedding_backend=args.embedding_backend,
            )
        )
    )
    report = evaluate_eval_set(load_eval_set(args.eval_set), retriever=retriever, top_k=args.top_k)
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
    summaries = report["summaries"]
    total_cases = sum(summary["case_count"] for summary in summaries)
    return {
        "rag_recall_at5": _weighted_average(summaries, "recall_at_5", total_cases),
        "rag_mrr": _weighted_average(summaries, "mrr", total_cases),
        "evaluated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def _weighted_average(summaries: list[dict[str, Any]], metric: str, total_cases: int) -> float:
    if total_cases == 0:
        return 0.0
    return sum(summary[metric] * summary["case_count"] for summary in summaries) / total_cases


def _format_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# RAG Evaluation Report",
        "",
        f"- Cases: {report['case_count']}",
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
    return "\n".join(lines)


def _evaluate_case(
    case: EvalCase,
    *,
    retriever: RuleRetriever | Any,
    top_k: int,
) -> EvalCaseResult:
    response = retriever.search(
        RagSearchRequest(
            query=case.query,
            top_k=top_k,
            min_score=0.0,
            scenario_type=case.scenario_type,
        )
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
    retriever = RuleRetriever(
        store=ChromaRuleStore(
            chunks_path=chunks_path,
            chroma_path=chroma_path,
            embedding_backend=embedding_backend,
        )
    )
    return LegacyEvalSummary(
        mode=mode,
        case_results=[_evaluate_smoke_case(retriever, case, mode=mode) for case in SMOKE_CASES],
    )


def _evaluate_smoke_case(retriever: RuleRetriever, case: SmokeCase, *, mode: str) -> LegacyCaseResult:
    response = retriever.search(_request_for_mode(case.query, mode=mode))
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


def _request_for_mode(query: str, *, mode: str) -> RagSearchRequest:
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
