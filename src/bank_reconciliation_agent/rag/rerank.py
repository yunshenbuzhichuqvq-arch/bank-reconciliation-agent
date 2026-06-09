from __future__ import annotations

import re
from typing import Protocol

from bank_reconciliation_agent.rag.fusion import FusedHit


TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+")


class Reranker(Protocol):
    def rerank(self, query: str, items: list[FusedHit], top_k: int) -> list[FusedHit]: ...


class LexicalReranker:
    def rerank(self, query: str, items: list[FusedHit], top_k: int) -> list[FusedHit]:
        if top_k <= 0 or not items:
            return []

        query_tokens = _tokenize(query)
        ranked: list[FusedHit] = []
        for item in items:
            overlap_ratio = _overlap_ratio(query_tokens, _tokenize(item.content))
            retrieval_signal = _retrieval_signal(item)
            reranker_score = (overlap_ratio * 0.7) + (retrieval_signal * 0.3)
            ranked.append(
                FusedHit(
                    chunk_id=item.chunk_id,
                    dense_score=item.dense_score,
                    bm25_score=item.bm25_score,
                    fusion_score=item.fusion_score,
                    fusion_rank=item.fusion_rank,
                    metadata=dict(item.metadata),
                    content=item.content,
                    reranker_score=min(1.0, max(0.0, reranker_score)),
                )
            )

        ranked.sort(
            key=lambda item: (
                item.reranker_score or 0.0,
                item.fusion_score,
                item.dense_score or 0.0,
                item.bm25_score or 0.0,
            ),
            reverse=True,
        )
        return ranked[:top_k]


class BgeReranker:
    def rerank(self, query: str, items: list[FusedHit], top_k: int) -> list[FusedHit]:
        raise NotImplementedError("TODO V1/V2: implement BGE reranker with optional dependency")


def _tokenize(text: str) -> set[str]:
    tokens = set()
    lowered = text.lower()
    for token in TOKEN_PATTERN.findall(lowered):
        tokens.add(token)
        if "_" in token:
            tokens.update(part for part in token.split("_") if part)
        cjk_chars = [char for char in token if "\u4e00" <= char <= "\u9fff"]
        tokens.update(cjk_chars)
        tokens.update("".join(cjk_chars[index : index + 2]) for index in range(len(cjk_chars) - 1))
    return tokens


def _overlap_ratio(query_tokens: set[str], item_tokens: set[str]) -> float:
    if not query_tokens or not item_tokens:
        return 0.0
    return len(query_tokens & item_tokens) / len(query_tokens)


def _retrieval_signal(item: FusedHit) -> float:
    values = [value for value in (item.dense_score, item.fusion_score) if value is not None]
    if item.bm25_score is not None:
        values.append(item.bm25_score / (item.bm25_score + 1.0))
    if not values:
        return 0.0
    return min(1.0, sum(values) / len(values))
