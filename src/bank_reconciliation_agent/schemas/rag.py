from pydantic import BaseModel, Field


class RagSearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=3, ge=1, le=10)
    min_score: float = Field(default=0.0, ge=0.0)
    enable_rewrite: bool = False
    enable_hybrid: bool = False


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
