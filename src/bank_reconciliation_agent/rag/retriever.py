import json
import re
from pathlib import Path
from typing import Any

from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchRequest, RagSearchResponse


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CHUNKS_PATH = PROJECT_ROOT / "data/rag/rule_chunks.jsonl"
TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+")


class RuleRetriever:
    def __init__(self, chunks_path: Path = DEFAULT_CHUNKS_PATH) -> None:
        self.chunks_path = chunks_path

    def search(self, request: RagSearchRequest) -> RagSearchResponse:
        """Search traceable public-source rule chunks with a minimal lexical scorer."""
        query_tokens = _tokenize(request.query)
        scored_items = []

        for chunk in self._load_chunks():
            score = _score_chunk(query_tokens, chunk)
            if score > 0:
                scored_items.append((score, chunk))

        scored_items.sort(key=lambda item: (-item[0], item[1]["chunk_id"]))
        return RagSearchResponse(
            items=[
                RagSearchItem(
                    chunk_id=chunk["chunk_id"],
                    source=f"{chunk['source_file']}#{chunk['section_title']}",
                    source_name=chunk["source_name"],
                    source_url=chunk["source_url"],
                    source_file=chunk["source_file"],
                    section_title=chunk["section_title"],
                    element_type=chunk["element_type"],
                    business_tags=chunk["business_tags"],
                    score=score,
                    content=chunk["content"],
                )
                for score, chunk in scored_items[: request.top_k]
            ]
        )

    def _load_chunks(self) -> list[dict[str, Any]]:
        if not self.chunks_path.exists():
            return []
        return [
            json.loads(line)
            for line in self.chunks_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


def _score_chunk(query_tokens: set[str], chunk: dict[str, Any]) -> float:
    searchable_text = " ".join(
        [
            chunk["section_title"],
            chunk["content"],
            " ".join(chunk["business_tags"]),
        ]
    )
    chunk_tokens = _tokenize(searchable_text)
    token_hits = len(query_tokens & chunk_tokens)
    tag_hits = sum(1 for tag in chunk["business_tags"] if tag in query_tokens)
    return float(token_hits + tag_hits * 2)


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
