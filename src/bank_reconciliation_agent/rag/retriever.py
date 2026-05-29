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
        collection_name: str = "mvp0_rule_chunks",
    ) -> None:
        self.chunks_path = chunks_path
        self.chroma_path = chroma_path or Path(settings.chroma_path)
        self.collection_name = collection_name
        self.embedding_function = HashEmbeddingFunction()
        self._collection: Collection | None = None

    def collection(self) -> Collection:
        if self._collection is None:
            self.chroma_path.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(self.chroma_path))
            self._collection = client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=self.embedding_function,
            )
            self._sync_chunks()
        return self._collection

    def count(self) -> int:
        return self.collection().count()

    def query(self, query_text: str, top_k: int) -> list[tuple[float, dict[str, Any], str]]:
        result = self.collection().query(
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

    def _sync_chunks(self) -> None:
        chunks = self._load_chunks()
        if not chunks:
            return

        collection = self.collection()
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


class RuleRetriever:
    def __init__(
        self,
        chunks_path: Path = DEFAULT_CHUNKS_PATH,
        chroma_path: Path | None = None,
    ) -> None:
        self.store = ChromaRuleStore(chunks_path=chunks_path, chroma_path=chroma_path)

    def search(self, request: RagSearchRequest) -> RagSearchResponse:
        """Search traceable public-source rule chunks with ChromaDB Top-K retrieval."""
        top_k = max(1, min(request.top_k, self.store.count()))
        results = self.store.query(query_text=request.query, top_k=top_k)
        threshold = max(request.min_score, 0.0)
        return RagSearchResponse(
            items=[
                self._to_search_item(score, metadata, content)
                for score, metadata, content in results
                if score > threshold
            ]
        )

    def collection_count(self) -> int:
        return self.store.count()

    def _to_search_item(
        self,
        score: float,
        metadata: dict[str, Any],
        content: str,
    ) -> RagSearchItem:
        return RagSearchItem(
            chunk_id=str(metadata["chunk_id"]),
            source=f"{metadata['source_file']}#{metadata['section_title']}",
            source_name=str(metadata["source_name"]),
            source_url=str(metadata["source_url"]),
            source_file=str(metadata["source_file"]),
            section_title=str(metadata["section_title"]),
            element_type=str(metadata["element_type"]),
            business_tags=json.loads(str(metadata["business_tags"])),
            score=score,
            content=content,
        )


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
