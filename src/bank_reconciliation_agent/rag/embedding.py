from __future__ import annotations

from typing import Protocol

from bank_reconciliation_agent.rag.retriever import _embed_text


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbeddingProvider:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_embed_text(text) for text in texts]
