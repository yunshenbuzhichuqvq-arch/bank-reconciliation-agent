from pydantic import BaseModel, Field


class RagSearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=3, ge=1, le=10)


class RagSearchItem(BaseModel):
    chunk_id: str
    source: str
    source_name: str
    source_url: str
    source_file: str
    section_title: str
    element_type: str
    business_tags: list[str]
    score: float
    content: str


class RagSearchResponse(BaseModel):
    items: list[RagSearchItem]
