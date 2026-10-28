import uuid

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.models.domain import Document, DocumentChunk, DocumentStatus
from app.services.chunking import TextChunk


def get_document(session: Session, document_id: uuid.UUID) -> Document | None:
    return session.scalar(select(Document).where(Document.id == document_id))


def replace_chunks(
    session: Session,
    document: Document,
    chunks: list[TextChunk],
    vectors: list[list[float]],
) -> None:
    session.execute(
        delete(DocumentChunk).where(DocumentChunk.document_id == document.id)
    )
    session.add_all(
        DocumentChunk(
            workspace_id=document.workspace_id,
            knowledge_base_id=document.knowledge_base_id,
            document_id=document.id,
            position=chunk.position,
            content=chunk.content,
            token_count=chunk.token_count,
            embedding=vector,
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    )


def semantic_search(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    knowledge_base_id: uuid.UUID,
    query_vector: list[float],
    top_k: int,
) -> list[dict[str, object]]:
    # pgvector cosine distance (<=>); score is cosine similarity = 1 - distance.
    sql = text("""
        SELECT dc.document_id, dc.content,
               1 - (dc.embedding <=> CAST(:query_vector AS vector)) AS score
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        WHERE dc.workspace_id = :workspace_id
          AND dc.knowledge_base_id = :knowledge_base_id
          AND d.status = 'READY'
        ORDER BY dc.embedding <=> CAST(:query_vector AS vector)
        LIMIT :top_k
    """)
    rows = session.execute(
        sql,
        {
            "workspace_id": workspace_id,
            "knowledge_base_id": knowledge_base_id,
            "query_vector": str(query_vector),
            "top_k": top_k,
        },
    ).mappings()
    return [dict(row) for row in rows]


def mark_status(
    session: Session,
    document: Document,
    status: DocumentStatus,
    reason: str | None = None,
) -> None:
    document.status = status
    document.failure_reason = reason
    session.add(document)
