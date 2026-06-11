from __future__ import annotations

from collections import Counter
from decimal import Decimal

from fastapi import APIRouter, HTTPException

from bank_reconciliation_agent.api.dependencies import CurrentUserId
from bank_reconciliation_agent.schemas.common import ApiResponse
from bank_reconciliation_agent.schemas.memory import MemoryContextResponse
from bank_reconciliation_agent.services.memory.long_term import long_term_memory_service
from bank_reconciliation_agent.services.memory.short_term import short_term_memory_service
from bank_reconciliation_agent.services.memory.summary import summary_memory_service


router = APIRouter()


@router.get("/{user_id}/context", response_model=ApiResponse[MemoryContextResponse])
async def get_memory_context(
    user_id: str,
    thread_id: str,
    error_type: str,
    current_user_id: CurrentUserId,
) -> ApiResponse[MemoryContextResponse]:
    if user_id != current_user_id:
        raise HTTPException(status_code=403, detail="forbidden user access")

    short_rows = short_term_memory_service.recent(thread_id=thread_id, limit=1000)
    summary = summary_memory_service.get(thread_id=thread_id)
    long_rows = long_term_memory_service.recall(
        user_id=user_id,
        error_type=error_type,
        keywords=[error_type.lower()],
        limit=1000,
    )

    response = MemoryContextResponse(
        short_term={
            "recent_decisions": len(short_rows),
            "summary": _summary_text(summary),
        },
        long_term={
            "similar_cases": len(long_rows),
            "historical_pattern": _historical_pattern(long_rows),
            "avg_confidence": _avg_confidence(long_rows),
        },
    )
    return ApiResponse(data=response)


def _summary_text(summary: dict[str, object] | None) -> str | None:
    if summary is None:
        return None
    value = summary.get("summary_text")
    return value if isinstance(value, str) and value else None


def _historical_pattern(rows: list[dict[str, object]]) -> str | None:
    decisions = [str(row["human_decision"]) for row in rows if row.get("human_decision")]
    if not decisions:
        return None
    return Counter(decisions).most_common(1)[0][0]


def _avg_confidence(rows: list[dict[str, object]]) -> float | None:
    confidences = [_as_decimal(row.get("ai_confidence")) for row in rows]
    valid_confidences = [confidence for confidence in confidences if confidence is not None]
    if not valid_confidences:
        return None
    average = sum(valid_confidences, start=Decimal("0")) / Decimal(len(valid_confidences))
    return float(average.quantize(Decimal("0.0001")))


def _as_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None
