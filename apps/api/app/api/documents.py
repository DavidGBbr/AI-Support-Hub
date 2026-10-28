import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.models.domain import Document, DocumentOutbox, KnowledgeBase
from app.schemas.documents import DocumentResponse
from app.services.extraction import MAX_FILE_BYTES, SUPPORTED_SUFFIXES

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/knowledge-bases/{knowledge_base_id}/documents"
)


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
def upload_document(
    workspace_id: uuid.UUID,
    knowledge_base_id: uuid.UUID,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> Document:
    kb = session.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.workspace_id == workspace_id,
        )
    )
    if kb is None:
        raise HTTPException(status_code=404, detail="knowledge base not found")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(status_code=415, detail="unsupported document type")
    content = file.file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="document exceeds the 10 MiB limit")

    document_id = uuid.uuid4()
    storage_dir = (
        Path(get_settings().document_storage_dir)
        / str(workspace_id)
        / str(knowledge_base_id)
    )
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_path = storage_dir / f"{document_id}{suffix}"
    storage_path.write_bytes(content)

    document = Document(
        id=document_id,
        workspace_id=workspace_id,
        knowledge_base_id=knowledge_base_id,
        filename=file.filename or storage_path.name,
        content_type=file.content_type or "application/octet-stream",
        storage_path=str(storage_path),
        size_bytes=len(content),
    )
    session.add(document)
    # Flush assigns database defaults, but document and intent commit together.
    session.flush()
    session.add(DocumentOutbox(document_id=document_id))
    session.commit()
    session.refresh(document)
    return document


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    workspace_id: uuid.UUID,
    knowledge_base_id: uuid.UUID,
    document_id: uuid.UUID,
    session: Session = Depends(get_session),
) -> Document:
    document = session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.workspace_id == workspace_id,
            Document.knowledge_base_id == knowledge_base_id,
        )
    )
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    return document
