from __future__ import annotations

from typing import Any

import jieba
from rank_bm25 import BM25Okapi


class Bm25Index:
    def __init__(self) -> None:
        self.chunk_ids: set[str] = set()
        self._chunks_by_id: dict[str, dict[str, Any]] = {}
        self._ordered_chunk_ids: list[str] = []
        self._bm25: BM25Okapi | None = None

    def build(self, chunks: list[dict[str, Any]]) -> None:
        self._chunks_by_id = {str(chunk["chunk_id"]): chunk for chunk in chunks}
        self._ordered_chunk_ids = [str(chunk["chunk_id"]) for chunk in chunks]
        self.chunk_ids = set(self._ordered_chunk_ids)
        tokenized_corpus = [self._tokenize(str(chunk["content"])) for chunk in chunks]
        self._bm25 = BM25Okapi(tokenized_corpus)

    def query(self, text: str, top_k: int) -> list[tuple[str, float]]:
        if self._bm25 is None or top_k <= 0:
            return []

        scores = self._bm25.get_scores(self._tokenize(text))
        ranked = sorted(
            zip(self._ordered_chunk_ids, scores, strict=True),
            key=lambda item: item[1],
            reverse=True,
        )
        return [
            (chunk_id, float(score))
            for chunk_id, score in ranked[:top_k]
            if score > 0
        ]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [token.strip().lower() for token in jieba.cut_for_search(text) if token.strip()]
