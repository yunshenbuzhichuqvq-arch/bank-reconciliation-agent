from pydantic import BaseModel


class ShortTermMemoryContextResponse(BaseModel):
    recent_decisions: int
    summary: str | None


class LongTermMemoryContextResponse(BaseModel):
    similar_cases: int
    historical_pattern: str | None
    avg_confidence: float | None


class MemoryContextResponse(BaseModel):
    short_term: ShortTermMemoryContextResponse
    long_term: LongTermMemoryContextResponse
