import uuid

from app.core.celery import celery_app
from app.core.db import SessionLocal
from app.services.ingestion import process_document


@celery_app.task(
    name="documents.process",
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def process_document_task(document_id: str, outbox_id: str | None = None) -> None:
    with SessionLocal() as session:
        process_document(
            session,
            uuid.UUID(document_id),
            outbox_id=uuid.UUID(outbox_id) if outbox_id else None,
        )
