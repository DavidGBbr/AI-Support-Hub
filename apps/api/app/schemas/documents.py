import uuid

from pydantic import BaseModel

from app.models.domain import DocumentStatus


class DocumentResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    knowledge_base_id: uuid.UUID
    filename: str
    size_bytes: int
    status: DocumentStatus
    failure_reason: str | None

    model_config = {"from_attributes": True}
