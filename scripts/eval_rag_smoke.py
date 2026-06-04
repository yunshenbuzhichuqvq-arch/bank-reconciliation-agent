from __future__ import annotations

import json
import sys
from pathlib import Path

from bank_reconciliation_agent.rag.retriever import rule_retriever
from bank_reconciliation_agent.schemas.rag import RagSearchRequest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_PATH = PROJECT_ROOT / "data/rag/smoke_eval.json"


def main() -> int:
    cases = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    failures = 0

    for index, case in enumerate(cases, start=1):
        response = rule_retriever.search(
            RagSearchRequest(query=case["query"], top_k=3, min_score=0.0)
        )
        best_score = response.items[0].score if response.items else 0.0
        chunk_ids = [item.chunk_id for item in response.items]
        matched = any(
            chunk_id.startswith(case["expect_chunk_id_prefix"])
            for chunk_id in chunk_ids
        )
        status = "hit" if matched else "miss"
        print(
            f"{index}. {status} prefix={case['expect_chunk_id_prefix']} "
            f"best_score={best_score:.4f} chunks={chunk_ids}"
        )
        if not matched:
            failures += 1

    if failures:
        print(f"rag smoke failed: {failures}/{len(cases)} miss")
        return 1
    print(f"rag smoke passed: {len(cases)}/{len(cases)} hit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
