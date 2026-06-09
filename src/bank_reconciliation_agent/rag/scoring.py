from __future__ import annotations

from bank_reconciliation_agent.schemas.rag import RagSearchItem


def representative_score(item: RagSearchItem) -> float | None:
    if item.reranker_score is not None:
        return item.reranker_score
    if item.dense_score is not None:
        return item.dense_score
    return item.score
