import uuid

from pydantic import BaseModel, Field


class SemanticSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000)
    top_k: int = Field(default=5, ge=1, le=20)


class SemanticSearchResult(BaseModel):
    document_id: uuid.UUID
    content: str
    score: float


class SemanticSearchResponse(BaseModel):
    results: list[SemanticSearchResult]
    duration_ms: float
