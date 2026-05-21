from pydantic import BaseModel, Field


class RagSearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=3, ge=1, le=10)


class RagSearchItem(BaseModel):
    source: str
    score: float
    content: str


class RagSearchResponse(BaseModel):
    items: list[RagSearchItem]

