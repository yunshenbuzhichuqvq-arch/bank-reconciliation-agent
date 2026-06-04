from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACE_DB_PATH = Path("/private/tmp/bank_reconciliation_agent_trace.sqlite")
os.environ["MYSQL_DSN"] = f"sqlite:///{TRACE_DB_PATH}"

from fastapi import UploadFile  # noqa: E402

from bank_reconciliation_agent.schemas.ledger import LedgerQuery  # noqa: E402
from bank_reconciliation_agent.rag.retriever import rule_retriever  # noqa: E402
from bank_reconciliation_agent.services.ledger import ledger_service  # noqa: E402
from bank_reconciliation_agent.services.rag_log import rag_log_service  # noqa: E402
from bank_reconciliation_agent.services.reconciliation import reconciliation_service  # noqa: E402
from scripts.generate_mock_excel import generate_mock_excel  # noqa: E402


FLOW_ID = "F1004"
SCENARIO_TYPE = "BANK_ENTERPRISE"
OUTPUT_PATH = PROJECT_ROOT / "local_traces" / f"{FLOW_ID}.json"


async def main() -> None:
    if TRACE_DB_PATH.exists():
        TRACE_DB_PATH.unlink()

    source_a_path, source_b_path = _mock_paths()
    task_id = await _upload(source_a_path, source_b_path)
    exceptions = reconciliation_service.get_exceptions(task_id=task_id, user_id="demo_user")
    exception = next(item for item in exceptions.items if item.flow_id == FLOW_ID)
    ledger_row = ledger_service.list(
        LedgerQuery(
            task_id=task_id,
            user_id="demo_user",
            scenario_type=SCENARIO_TYPE,
            page=1,
            page_size=100,
        )
    ).items
    persisted = next(row for row in ledger_row if row.flow_id == FLOW_ID)
    rag_log = rag_log_service.get_latest_row(task_id, "AMOUNT_MISMATCH", user_id="demo_user")
    if rag_log is None:
        raise RuntimeError("RAG retrieval log not found for AMOUNT_MISMATCH")

    hits = [
        {
            "chunk_id": item.chunk_id,
            "score": item.score,
            "source": item.source,
        }
        for item in rule_retriever.get_by_chunk_ids(rag_log["sources"])
    ]
    trace = {
        "flow_id": FLOW_ID,
        "scenario_type": SCENARIO_TYPE,
        "error_type": exception.error_type,
        "input": {
            "source_a_amount": exception.source_a_amount,
            "source_b_amount": exception.source_b_amount,
            "amount_diff": exception.amount_diff,
        },
        "rag": {
            "query": rag_log["query_text"],
            "top_k": rag_log["top_k"],
            "hits": hits,
        },
        "agent_output": {
            "decision": exception.audit_decision.decision,
            "risk_level": exception.audit_decision.risk_level,
            "reason": exception.audit_decision.reason,
            "confidence": exception.audit_decision.confidence,
        },
        "persisted": {
            "handle_status": persisted.handle_status,
            "discrepancy_amount": f"{persisted.discrepancy_amount:.2f}",
        },
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(trace, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT_PATH}")


async def _upload(source_a_path: Path, source_b_path: Path) -> str:
    with source_a_path.open("rb") as source_a_file, source_b_path.open("rb") as source_b_file:
        response = await reconciliation_service.upload(
            source_a_file=UploadFile(source_a_file, filename=source_a_path.name),
            source_b_file=UploadFile(source_b_file, filename=source_b_path.name),
            user_id="demo_user",
            scenario_type=SCENARIO_TYPE,
        )
    return response.task_id


def _mock_paths() -> tuple[Path, Path]:
    source_a_path = PROJECT_ROOT / "mock_data" / "source_a_enterprise_book.xlsx"
    source_b_path = PROJECT_ROOT / "mock_data" / "source_b_bank_statement.xlsx"
    if source_a_path.exists() and source_b_path.exists():
        return source_a_path, source_b_path
    return generate_mock_excel(Path("/private/tmp/bank_reconciliation_agent_mock_data"))


if __name__ == "__main__":
    asyncio.run(main())
