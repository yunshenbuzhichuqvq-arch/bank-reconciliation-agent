from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.rag.scoring import representative_score
from bank_reconciliation_agent.rag.retriever import DEFAULT_CHUNKS_PATH, RuleRetriever
from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchRequest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class SmokeCase:
    query: str
    expected_tag: str


@dataclass(frozen=True)
class CaseResult:
    query: str
    expected_tag: str
    matched_chunk_id: str | None
    representative_score: float | None
    reranker_score: float | None
    hit: bool
    triggers_l1_to_l2: bool


@dataclass(frozen=True)
class EvalSummary:
    mode: str
    case_results: list[CaseResult]

    @property
    def hit_count(self) -> int:
        return sum(result.hit for result in self.case_results)

    @property
    def average_reranker_score(self) -> float:
        scores = [
            result.reranker_score
            for result in self.case_results
            if result.reranker_score is not None
        ]
        if not scores:
            return 0.0
        return sum(scores) / len(scores)

    @property
    def l1_to_l2_trigger_rate(self) -> float:
        if not self.case_results:
            return 0.0
        triggered = sum(result.triggers_l1_to_l2 for result in self.case_results)
        return triggered / len(self.case_results)


SMOKE_CASES = [
    SmokeCase(
        query="金额差异 对账不平 银行端 清算端 金额",
        expected_tag="amount_mismatch",
    ),
    SmokeCase(
        query="单边缺失 查询查复 来源文件",
        expected_tag="single_side_missing",
    ),
    SmokeCase(
        query="差错 台账 审计 留痕 task_id flow_id",
        expected_tag="audit_trail",
    ),
    SmokeCase(
        query="流水缺失 T+1 追溯 查询查复",
        expected_tag="single_side_missing",
    ),
]


def evaluate_cases(
    *,
    chunks_path: Path = DEFAULT_CHUNKS_PATH,
    chroma_path: Path = PROJECT_ROOT / "chroma_eval",
    mode: str,
) -> EvalSummary:
    retriever = RuleRetriever(chunks_path=chunks_path, chroma_path=chroma_path)
    return EvalSummary(
        mode=mode,
        case_results=[
            _evaluate_case(retriever, case, mode=mode)
            for case in SMOKE_CASES
        ],
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run smoke evaluation for dense vs hybrid RAG retrieval.")
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS_PATH)
    parser.add_argument("--chroma", type=Path, default=PROJECT_ROOT / "chroma_eval")
    args = parser.parse_args(argv)

    dense_summary = evaluate_cases(
        chunks_path=args.chunks,
        chroma_path=args.chroma / "dense",
        mode="dense",
    )
    hybrid_summary = evaluate_cases(
        chunks_path=args.chunks,
        chroma_path=args.chroma / "hybrid_rerank",
        mode="hybrid_rerank",
    )

    print("mode\thit_count\tcase_count\tavg_reranker_score\tl1_to_l2_trigger_rate")
    for summary in (dense_summary, hybrid_summary):
        print(
            f"{summary.mode}\t{summary.hit_count}\t{len(summary.case_results)}\t"
            f"{summary.average_reranker_score:.4f}\t{summary.l1_to_l2_trigger_rate:.4f}"
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


def _evaluate_case(retriever: RuleRetriever, case: SmokeCase, *, mode: str) -> CaseResult:
    request = _request_for_mode(case.query, mode=mode)
    response = retriever.search(request)
    matched_item = _find_hit(response.items, expected_tag=case.expected_tag)
    score = representative_score(matched_item) if matched_item is not None else None
    return CaseResult(
        query=case.query,
        expected_tag=case.expected_tag,
        matched_chunk_id=matched_item.chunk_id if matched_item is not None else None,
        representative_score=score,
        reranker_score=matched_item.reranker_score if matched_item is not None else None,
        hit=matched_item is not None,
        triggers_l1_to_l2=score is None or score < settings.rag_low_score,
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


if __name__ == "__main__":
    main()
