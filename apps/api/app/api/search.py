import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.schemas.search import SemanticSearchRequest, SemanticSearchResponse
from app.services.search import search_chunks

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/knowledge-bases/{knowledge_base_id}"
)


@router.post("/search", response_model=SemanticSearchResponse)
def semantic_search_endpoint(
    workspace_id: uuid.UUID,
    knowledge_base_id: uuid.UUID,
    payload: SemanticSearchRequest,
    session: Session = Depends(get_session),
) -> SemanticSearchResponse:
    try:
        results, duration_ms = search_chunks(
            session,
            workspace_id=workspace_id,
            knowledge_base_id=knowledge_base_id,
            query=payload.query,
            top_k=payload.top_k,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SemanticSearchResponse(results=results, duration_ms=duration_ms)
