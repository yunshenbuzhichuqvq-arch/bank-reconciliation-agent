from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class FusedHit:
    chunk_id: str
    dense_score: float | None
    bm25_score: float | None
    fusion_score: float
    fusion_rank: int
    metadata: dict[str, Any]
    content: str
    reranker_score: float | None = None


def fuse_rrf(
    dense: list[tuple[float, dict[str, Any], str]],
    sparse: list[tuple[str, float]],
    k: int = 60,
) -> list[FusedHit]:
    fused: dict[str, FusedHit] = {}

    for rank, (dense_score, metadata, content) in enumerate(dense, start=1):
        chunk_id = str(metadata["chunk_id"])
        fused[chunk_id] = FusedHit(
            chunk_id=chunk_id,
            dense_score=dense_score,
            bm25_score=None,
            fusion_score=1.0 / (k + rank),
            fusion_rank=0,
            metadata=dict(metadata),
            content=content,
        )

    for rank, (chunk_id, bm25_score) in enumerate(sparse, start=1):
        hit = fused.get(chunk_id)
        if hit is None:
            hit = FusedHit(
                chunk_id=chunk_id,
                dense_score=None,
                bm25_score=bm25_score,
                fusion_score=0.0,
                fusion_rank=0,
                metadata={"chunk_id": chunk_id},
                content="",
            )
            fused[chunk_id] = hit
        else:
            hit.bm25_score = bm25_score
        hit.fusion_score += 1.0 / (k + rank)

    ranked = sorted(
        fused.values(),
        key=lambda hit: (hit.fusion_score, hit.dense_score or 0.0, hit.bm25_score or 0.0),
        reverse=True,
    )
    for index, hit in enumerate(ranked, start=1):
        hit.fusion_rank = index
    return ranked
