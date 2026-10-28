"""PostgreSQL-backed publisher; run independently of Celery and its broker."""

import argparse
import logging
import signal
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from threading import Event

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models.domain import DocumentOutbox

logger = logging.getLogger(__name__)
SAFE_PUBLISH_ERROR = "ingestion task publication failed; retry scheduled"


def publish_ingestion(event: DocumentOutbox) -> None:
    # Lazy import avoids depending on Celery task registration at module import.
    from app.core.celery import celery_app

    celery_app.send_task(
        "documents.process",
        args=[str(event.document_id), str(event.id)],
        task_id=str(event.id),
        retry=False,
    )


def dispatch_one(
    session: Session,
    publish: Callable[[DocumentOutbox], None] = publish_ingestion,
) -> bool:
    event = session.scalar(
        select(DocumentOutbox)
        .where(
            DocumentOutbox.published_at.is_(None),
            DocumentOutbox.processed_at.is_(None),
            DocumentOutbox.next_attempt_at <= func.now(),
        )
        .order_by(DocumentOutbox.next_attempt_at, DocumentOutbox.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if event is None:
        session.rollback()
        return False

    event.attempts += 1
    try:
        publish(event)
    except Exception:
        event.last_error = SAFE_PUBLISH_ERROR
        event.next_attempt_at = datetime.now(UTC) + timedelta(
            seconds=min(2 ** min(event.attempts, 9), 300)
        )
        logger.warning("outbox_publish_retry event_id=%s", event.id)
    else:
        event.published_at = datetime.now(UTC)
        event.last_error = None
    # If the process/commit fails after publish, the intent remains eligible.
    # Delivery is at least once; ingestion deduplicates by event ID in PostgreSQL.
    session.commit()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Attempt one due event")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    stop = Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    while not stop.is_set():
        try:
            with SessionLocal() as session:
                dispatched = dispatch_one(session)
        except Exception:
            logger.exception("outbox_dispatcher_database_error")
            dispatched = False
            if args.once:
                raise
        if args.once:
            break
        if not dispatched:
            stop.wait(1)


if __name__ == "__main__":
    main()
