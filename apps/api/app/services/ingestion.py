import logging
import time
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.domain import DocumentOutbox, DocumentStatus
from app.repositories.documents import get_document, mark_status, replace_chunks
from app.services.chunking import chunk_text
from app.services.embeddings import EmbeddingProvider, OpenAIEmbeddingProvider
from app.services.extraction import DocumentExtractionError, extract_text

logger = logging.getLogger(__name__)
SAFE_FAILURE_MESSAGE = "document processing failed"


class DocumentNotFoundError(LookupError):
    pass


def process_document(
    session: Session,
    document_id: uuid.UUID,
    provider: EmbeddingProvider | None = None,
    *,
    outbox_id: uuid.UUID | None = None,
) -> None:
    event = None
    if outbox_id is not None:
        # Hold this row lock through extraction, embedding, and final commit.
        # Concurrent/redelivered tasks cannot process the same intent twice.
        event = session.scalar(
            select(DocumentOutbox)
            .where(
                DocumentOutbox.id == outbox_id,
                DocumentOutbox.document_id == document_id,
            )
            .with_for_update()
        )
        if event is None or event.processed_at is not None:
            session.rollback()
            return
    document = get_document(session, document_id)
    if document is None:
        raise DocumentNotFoundError(str(document_id))

    mark_status(session, document, DocumentStatus.PROCESSING)
    if event is None:
        session.commit()
    else:
        session.flush()
    started = time.perf_counter()
    try:
        extracted = extract_text(document.storage_path)
        chunks = chunk_text(extracted.text)
        if not chunks:
            raise DocumentExtractionError("document has no useful textual content")
        embedding_provider = provider or OpenAIEmbeddingProvider()
        vectors = embedding_provider.embed([chunk.content for chunk in chunks])
        if len(vectors) != len(chunks):
            raise RuntimeError("embedding count does not match chunk count")

        # Replacement and READY transition share one transaction. Old vectors are
        # removed only after extraction/embedding succeeds, keeping reprocessing safe.
        replace_chunks(session, document, chunks, vectors)
        mark_status(session, document, DocumentStatus.READY)
        if event is not None:
            event.processed_at = func.now()
        session.commit()
        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "document_ingestion_complete document_id=%s duration_ms=%.2f chunks=%d",
            document.id,
            duration_ms,
            len(chunks),
        )
    except Exception:
        session.rollback()
        # A concurrent retry may have completed after rollback released our lock.
        completed = False
        if outbox_id is not None:
            current_event = session.scalar(
                select(DocumentOutbox)
                .where(DocumentOutbox.id == outbox_id)
                .with_for_update()
            )
            completed = current_event is None or current_event.processed_at is not None
        current = get_document(session, document_id)
        if current is not None and not completed:
            mark_status(
                session,
                current,
                DocumentStatus.FAILED,
                SAFE_FAILURE_MESSAGE,
            )
        session.commit()
        logger.exception("document_ingestion_failed document_id=%s", document_id)
        raise
