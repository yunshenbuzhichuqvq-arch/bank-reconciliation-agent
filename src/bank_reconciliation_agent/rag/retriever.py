from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.api.types import EmbeddingFunction

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.core.logging import log
from bank_reconciliation_agent.rag.fusion import FusedHit, fuse_rrf
from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchRequest, RagSearchResponse


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CHUNKS_PATH = PROJECT_ROOT / "data/rag/rule_chunks.jsonl"
TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+")
EMBEDDING_DIMENSIONS = 128


class HashEmbeddingFunction(EmbeddingFunction[list[str]]):
    """Deterministic local embeddings for MVP-0, avoiding external model downloads."""

    def __init__(self) -> None:
        pass

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [_embed_text(text) for text in input]

    @staticmethod
    def name() -> str:
        return "bank_reconciliation_hash_embedding"

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> "HashEmbeddingFunction":
        return HashEmbeddingFunction()

    def get_config(self) -> dict[str, Any]:
        return {"dimensions": EMBEDDING_DIMENSIONS}


class ChromaRuleStore:
    def __init__(
        self,
        chunks_path: Path = DEFAULT_CHUNKS_PATH,
        chroma_path: Path | None = None,
        scenario_type: str = "BANK_ENTERPRISE",
        collection_name: str | None = None,
    ) -> None:
        self.chunks_path = chunks_path
        self.chroma_path = chroma_path or Path(settings.chroma_path)
        self.collection_name = collection_name or self._collection_name_for_scenario(scenario_type)
        self.embedding_function = HashEmbeddingFunction()
        self._collections: dict[str, Collection] = {}

    def collection(self, scenario_type: str = "BANK_ENTERPRISE") -> Collection:
        collection_name = self._collection_name_for_scenario(scenario_type)
        collection = self._collections.get(collection_name)
        if collection is None:
            self.chroma_path.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(self.chroma_path))
            collection = client.get_or_create_collection(
                name=collection_name,
                embedding_function=self.embedding_function,
            )
            self._collections[collection_name] = collection
            self._sync_chunks(scenario_type)
        return collection

    def count(self) -> int:
        return self.collection().count()

    def query(
        self,
        query_text: str,
        top_k: int,
        scenario_type: str = "BANK_ENTERPRISE",
    ) -> list[tuple[float, dict[str, Any], str]]:
        result = self.collection(scenario_type=scenario_type).query(
            query_texts=[query_text],
            n_results=top_k,
            include=["documents", "distances", "metadatas"],
        )
        documents = result["documents"][0]
        distances = result["distances"][0]
        metadatas = result["metadatas"][0]
        return [
            (_score_from_distance(distance), dict(metadata), document)
            for distance, metadata, document in zip(distances, metadatas, documents, strict=True)
        ]

    def get_by_ids(
        self,
        chunk_ids: list[str],
        scenario_type: str = "BANK_ENTERPRISE",
    ) -> list[tuple[float, dict[str, Any], str]]:
        if not chunk_ids:
            return []
        result = self.collection(scenario_type=scenario_type).get(
            ids=chunk_ids,
            include=["documents", "metadatas"],
        )
        documents = result["documents"] or []
        metadatas = result["metadatas"] or []
        return [
            (0.0, dict(metadata), document)
            for metadata, document in zip(metadatas, documents, strict=True)
        ]

    def _sync_chunks(self, scenario_type: str) -> None:
        if scenario_type != "BANK_ENTERPRISE":
            return
        chunks = self._load_chunks()
        if not chunks:
            return

        collection = self.collection(scenario_type=scenario_type)
        collection.upsert(
            ids=[chunk["chunk_id"] for chunk in chunks],
            documents=[chunk["content"] for chunk in chunks],
            metadatas=[self._to_metadata(chunk) for chunk in chunks],
        )

    def _load_chunks(self) -> list[dict[str, Any]]:
        if not self.chunks_path.exists():
            return []
        return [
            json.loads(line)
            for line in self.chunks_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def _to_metadata(self, chunk: dict[str, Any]) -> dict[str, str | int | float | bool | None]:
        return {
            "chunk_id": chunk["chunk_id"],
            "source_name": chunk["source_name"],
            "source_url": chunk["source_url"],
            "source_file": chunk["source_file"],
            "source_type": chunk["source_type"],
            "section_title": chunk["section_title"],
            "page_no": chunk["page_no"],
            "element_type": chunk["element_type"],
            "business_tags": json.dumps(chunk["business_tags"], ensure_ascii=False),
        }

    @staticmethod
    def _collection_name_for_scenario(scenario_type: str) -> str:
        return f"rule_chunks_{scenario_type.lower()}"


class RuleRetriever:
    def __init__(
        self,
        chunks_path: Path = DEFAULT_CHUNKS_PATH,
        chroma_path: Path | None = None,
        *,
        store: ChromaRuleStore | None = None,
        rewriter: Any | None = None,
        sparse_index: Any | None = None,
        reranker: Any | None = None,
    ) -> None:
        self.store = store or ChromaRuleStore(chunks_path=chunks_path, chroma_path=chroma_path)
        self._rewriter = rewriter
        self._sparse_index = sparse_index
        self._reranker = reranker

    def search(self, request: RagSearchRequest) -> RagSearchResponse:
        """Search traceable public-source rule chunks with configurable retrieval orchestration."""
        dense_top_k = max(
            1,
            min(settings.rag_dense_top_n, self.store.collection(request.scenario_type).count()),
        )
        rewritten_query = None
        query_text = request.query
        if request.enable_rewrite:
            rewriter = self._get_rewriter()
            if rewriter is not None:
                rewritten_query = rewriter.rewrite(
                    request.query,
                    scenario_type=request.scenario_type,
                )
                query_text = rewritten_query

        dense_results = self.store.query(
            query_text=query_text,
            top_k=dense_top_k,
            scenario_type=request.scenario_type,
        )
        hybrid_enabled = request.enable_hybrid
        sparse_index = None
        if hybrid_enabled:
            sparse_index = self._get_sparse_index()
            if sparse_index is None:
                hybrid_enabled = False

        if hybrid_enabled and sparse_index is not None:
            ranked_hits = fuse_rrf(
                dense_results,
                sparse_index.query(query_text, top_k=settings.rag_bm25_top_n),
                k=settings.rag_rrf_k,
            )
            self._backfill_sparse_only_hits(ranked_hits, scenario_type=request.scenario_type)
        else:
            ranked_hits = _as_fused_hits(dense_results)

        reranker_enabled = request.enable_reranker
        reranker = None
        if reranker_enabled:
            reranker = self._get_reranker()
            if reranker is None:
                reranker_enabled = False

        if reranker_enabled and reranker is not None:
            ranked_hits = reranker.rerank(
                query_text,
                ranked_hits,
                top_k=settings.rag_rerank_top_k,
            )
        else:
            ranked_hits = ranked_hits[: request.top_k]

        threshold = max(request.min_score, 0.0)
        return RagSearchResponse(
            items=[
                self._to_search_item(hit, reranker_enabled=reranker_enabled)
                for hit in ranked_hits
                if _passes_threshold(hit, threshold=threshold, reranker_enabled=reranker_enabled)
            ],
            rewritten_query=rewritten_query if request.enable_rewrite else None,
        )

    def collection_count(self) -> int:
        return self.store.count()

    def get_by_chunk_ids(
        self,
        chunk_ids: list[str],
        scenario_type: str = "BANK_ENTERPRISE",
    ) -> list[RagSearchItem]:
        return [
            self._to_search_item(
                FusedHit(
                    chunk_id=str(metadata["chunk_id"]),
                    dense_score=score if score > 0 else None,
                    bm25_score=None,
                    fusion_score=score,
                    fusion_rank=index,
                    metadata=dict(metadata),
                    content=content,
                ),
                reranker_enabled=False,
            )
            for index, (score, metadata, content) in enumerate(self.store.get_by_ids(
                chunk_ids,
                scenario_type=scenario_type,
            ), start=1)
        ]

    def _to_search_item(self, hit: FusedHit, *, reranker_enabled: bool) -> RagSearchItem:
        metadata = hit.metadata
        return RagSearchItem(
            chunk_id=str(metadata["chunk_id"]),
            source=f"{metadata['source_file']}#{metadata['section_title']}",
            source_name=str(metadata["source_name"]),
            source_url=str(metadata["source_url"]),
            source_file=str(metadata["source_file"]),
            section_title=str(metadata["section_title"]),
            element_type=str(metadata["element_type"]),
            business_tags=json.loads(str(metadata["business_tags"])),
            score=(hit.reranker_score or 0.0) if reranker_enabled else hit.dense_score or hit.fusion_score,
            content=hit.content,
            dense_score=hit.dense_score if hit.bm25_score is not None or reranker_enabled else None,
            bm25_score=hit.bm25_score,
            reranker_score=hit.reranker_score,
            fusion_rank=hit.fusion_rank if hit.bm25_score is not None or reranker_enabled else None,
        )

    def _backfill_sparse_only_hits(
        self,
        hits: list[FusedHit],
        *,
        scenario_type: str,
    ) -> None:
        chunk_ids = [hit.chunk_id for hit in hits if hit.dense_score is None]
        if not chunk_ids:
            return

        chunk_by_id = {
            str(metadata["chunk_id"]): (metadata, content)
            for _, metadata, content in self.store.get_by_ids(chunk_ids, scenario_type=scenario_type)
        }
        for hit in hits:
            if hit.dense_score is not None:
                continue
            metadata_and_content = chunk_by_id.get(hit.chunk_id)
            if metadata_and_content is None:
                continue
            metadata, content = metadata_and_content
            hit.metadata = dict(metadata)
            hit.content = content

    def _get_rewriter(self) -> Any | None:
        if self._rewriter is not None:
            return self._rewriter
        from bank_reconciliation_agent.rag.query_rewrite import QueryRewriter

        self._rewriter = QueryRewriter()
        return self._rewriter

    def _get_sparse_index(self) -> Any | None:
        if self._sparse_index is not None:
            return self._sparse_index
        try:
            from bank_reconciliation_agent.rag.sparse import Bm25Index
        except ImportError:
            log.warning("rag_hybrid_dependency_missing")
            return None
        chunks = self.store._load_chunks()
        index = Bm25Index()
        index.build(chunks)
        self._sparse_index = index
        return self._sparse_index

    def _get_reranker(self) -> Any | None:
        if self._reranker is not None:
            return self._reranker
        try:
            from bank_reconciliation_agent.rag.rerank import LexicalReranker
        except ImportError:
            log.warning("rag_reranker_dependency_missing")
            return None
        self._reranker = LexicalReranker()
        return self._reranker


def _as_fused_hits(dense_hits: list[tuple[float, dict[str, Any], str]]) -> list[FusedHit]:
    return [
        FusedHit(
            chunk_id=str(metadata["chunk_id"]),
            dense_score=score,
            bm25_score=None,
            fusion_score=score,
            fusion_rank=index,
            metadata=dict(metadata),
            content=content,
        )
        for index, (score, metadata, content) in enumerate(dense_hits, start=1)
    ]


def _passes_threshold(
    hit: FusedHit,
    *,
    threshold: float,
    reranker_enabled: bool,
) -> bool:
    if reranker_enabled:
        return (hit.reranker_score or 0.0) >= max(threshold, settings.rag_reranker_min_score)
    if hit.dense_score is not None:
        return hit.dense_score > threshold
    return hit.fusion_score > threshold


def _embed_text(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for token in _tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _score_from_distance(distance: float) -> float:
    return 1.0 / (1.0 + distance)


def _tokenize(text: str) -> set[str]:
    tokens = set()
    lowered = text.lower()
    for token in TOKEN_PATTERN.findall(lowered):
        tokens.add(token)
        if "_" in token:
            tokens.update(part for part in token.split("_") if part)
        cjk_chars = [char for char in token if "\u4e00" <= char <= "\u9fff"]
        tokens.update(cjk_chars)
        tokens.update(
            "".join(cjk_chars[index : index + 2])
            for index in range(len(cjk_chars) - 1)
        )
    return tokens


rule_retriever = RuleRetriever()
