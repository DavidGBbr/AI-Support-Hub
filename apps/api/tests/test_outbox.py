import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier
from unittest.mock import Mock

import pytest
from sqlalchemy import delete, event, func, select

from app.core.celery import celery_app
from app.core.config import get_settings
from app.core.db import SessionLocal, get_session
from app.main import app
from app.models.domain import (
    Document,
    DocumentChunk,
    DocumentOutbox,
    DocumentStatus,
    KnowledgeBase,
    Workspace,
)
from app.services.ingestion import process_document
from app.services.outbox import SAFE_PUBLISH_ERROR, dispatch_one

pytestmark = pytest.mark.pgvector


@pytest.fixture
def upload(client, tmp_path, monkeypatch):
    with SessionLocal() as session:
        session.execute(select(DocumentOutbox).limit(1))
        workspace = Workspace(name="Outbox tests")
        session.add(workspace)
        session.flush()
        kb = KnowledgeBase(workspace_id=workspace.id, name="Outbox KB")
        session.add(kb)
        session.commit()
        workspace_id, kb_id = workspace.id, kb.id
        monkeypatch.setattr(get_settings(), "document_storage_dir", str(tmp_path))
        app.dependency_overrides[get_session] = lambda: session

        def post():
            return client.post(
                f"/api/v1/workspaces/{workspace_id}/knowledge-bases/{kb_id}/documents",
                files={"file": ("policy.txt", b"Refund policy", "text/plain")},
            )

        try:
            yield post, session
        finally:
            app.dependency_overrides.pop(get_session, None)
            session.rollback()
            session.execute(delete(Workspace).where(Workspace.id == workspace_id))
            session.commit()


def uploaded(upload):
    response = upload[0]()
    assert response.status_code == 202
    document_id = uuid.UUID(response.json()["id"])
    with SessionLocal() as session:
        outbox_id = session.scalar(
            select(DocumentOutbox.id).where(DocumentOutbox.document_id == document_id)
        )
        assert outbox_id is not None
    return document_id, outbox_id


def provider():
    vector = [1.0] + [0.0] * (get_settings().embedding_dimensions - 1)
    return Mock(embed=Mock(side_effect=lambda texts: [vector.copy() for _ in texts]))


def assert_complete(document_id, outbox_id):
    with SessionLocal() as session:
        assert session.get(Document, document_id).status == DocumentStatus.READY
        assert session.get(DocumentOutbox, outbox_id).processed_at is not None
        assert (
            session.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
            )
            == 1
        )


def test_upload_commits_document_and_intent_without_broker(upload, monkeypatch):
    send = Mock(side_effect=RuntimeError("broker offline"))
    monkeypatch.setattr(celery_app, "send_task", send)
    document_id, outbox_id = uploaded(upload)
    send.assert_not_called()
    with SessionLocal() as session:
        document = session.get(Document, document_id)
        intent = session.get(DocumentOutbox, outbox_id)
        assert document.status == DocumentStatus.PENDING
        assert document.failure_reason is None
        assert Path(document.storage_path).read_bytes() == b"Refund policy"
        assert intent.published_at is None
        assert intent.attempts == 0


def test_failed_intent_insert_rolls_back_document_too(upload):
    def fail_insert(*_):
        raise RuntimeError("intent insert failed")

    event.listen(DocumentOutbox, "before_insert", fail_insert)
    try:
        with pytest.raises(RuntimeError, match="intent insert failed"):
            upload[0]()
    finally:
        event.remove(DocumentOutbox, "before_insert", fail_insert)
        upload[1].rollback()
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(Document)) == 0
        assert session.scalar(select(func.count()).select_from(DocumentOutbox)) == 0


def test_restart_after_upload_publishes_committed_intent(upload, monkeypatch):
    document_id, outbox_id = uploaded(upload)
    send = Mock()
    monkeypatch.setattr(celery_app, "send_task", send)
    # Fresh connection/process can discover the intent without any API callback.
    with SessionLocal() as dispatcher:
        assert dispatch_one(dispatcher)
        assert not dispatch_one(dispatcher)
    send.assert_called_once_with(
        "documents.process",
        args=[str(document_id), str(outbox_id)],
        task_id=str(outbox_id),
        retry=False,
    )
    with SessionLocal() as session:
        assert session.get(DocumentOutbox, outbox_id).published_at is not None
        assert session.get(Document, document_id).status == DocumentStatus.PENDING


def test_broker_failure_is_retained_and_retried_with_backoff(upload):
    document_id, outbox_id = uploaded(upload)
    fail = Mock(side_effect=RuntimeError("secret-broker-url"))
    with SessionLocal() as session:
        assert dispatch_one(session, fail)
        intent = session.get(DocumentOutbox, outbox_id)
        assert intent.published_at is None
        assert intent.attempts == 1
        assert intent.last_error == SAFE_PUBLISH_ERROR
        assert "secret" not in intent.last_error
        assert intent.next_attempt_at > datetime.now(UTC)
        assert session.get(Document, document_id).status == DocumentStatus.PENDING
    with SessionLocal() as session:
        assert not dispatch_one(session, fail)
    fail.assert_called_once()
    with SessionLocal() as session:
        session.get(DocumentOutbox, outbox_id).next_attempt_at = datetime.now(UTC)
        session.commit()
    send = Mock()
    with SessionLocal() as session:
        assert dispatch_one(session, send)
        intent = session.get(DocumentOutbox, outbox_id)
        assert intent.attempts == 2
        assert intent.published_at is not None
        assert intent.last_error is None
    send.assert_called_once()


@pytest.mark.parametrize("after_publish", [False, True])
def test_dispatcher_crash_releases_intent_and_republish_is_idempotent(
    upload,
    after_publish,
):
    document_id, outbox_id = uploaded(upload)
    accepted = []

    def crash(intent):
        if after_publish:
            accepted.append((intent.document_id, intent.id))
        raise SystemExit("dispatcher crashed")

    with pytest.raises(SystemExit), SessionLocal() as session:
        dispatch_one(session, crash)
    with SessionLocal() as session:
        intent = session.get(DocumentOutbox, outbox_id)
        assert intent.published_at is None
        assert intent.attempts == 0
        assert dispatch_one(
            session, lambda item: accepted.append((item.document_id, item.id))
        )
    embeddings = provider()
    for doc_id, event_id in accepted:
        with SessionLocal() as session:
            process_document(session, doc_id, embeddings, outbox_id=event_id)
    embeddings.embed.assert_called_once()
    assert_complete(document_id, outbox_id)


def test_competing_dispatcher_skips_locked_intent(upload):
    _, outbox_id = uploaded(upload)
    send = Mock()
    with SessionLocal() as first, SessionLocal() as second:
        first.scalar(
            select(DocumentOutbox)
            .where(DocumentOutbox.id == outbox_id)
            .with_for_update()
        )
        assert not dispatch_one(second, send)
        send.assert_not_called()
        first.rollback()
        assert dispatch_one(second, send)
    send.assert_called_once()


def test_concurrent_duplicate_consumers_only_embed_once(upload):
    document_id, outbox_id = uploaded(upload)
    embeddings = provider()
    barrier = Barrier(2)

    def consume():
        with SessionLocal() as session:
            barrier.wait(timeout=10)
            process_document(session, document_id, embeddings, outbox_id=outbox_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(consume)
        second = executor.submit(consume)
        first.result(timeout=20)
        second.result(timeout=20)
    embeddings.embed.assert_called_once()
    assert_complete(document_id, outbox_id)


def test_completion_marker_and_vectors_rollback_together(upload):
    document_id, outbox_id = uploaded(upload)
    embeddings = provider()

    def fail_completion(session):
        if any(
            isinstance(item, DocumentOutbox) and item.processed_at is not None
            for item in session.identity_map.values()
        ):
            raise RuntimeError("completion commit failed")

    with SessionLocal() as session:
        event.listen(session, "before_commit", fail_completion)
        with pytest.raises(RuntimeError, match="completion commit failed"):
            process_document(session, document_id, embeddings, outbox_id=outbox_id)
    with SessionLocal() as session:
        assert session.get(DocumentOutbox, outbox_id).processed_at is None
        assert session.get(Document, document_id).status == DocumentStatus.FAILED
        assert session.scalar(select(func.count()).select_from(DocumentChunk)) == 0
        process_document(session, document_id, embeddings, outbox_id=outbox_id)
    assert embeddings.embed.call_count == 2
    assert_complete(document_id, outbox_id)


def test_worker_crash_rolls_back_and_redelivery_recovers(upload):
    document_id, outbox_id = uploaded(upload)
    crashed = Mock(embed=Mock(side_effect=SystemExit("worker lost")))
    with pytest.raises(SystemExit), SessionLocal() as session:
        process_document(session, document_id, crashed, outbox_id=outbox_id)
    with SessionLocal() as session:
        assert session.get(DocumentOutbox, outbox_id).processed_at is None
        assert session.get(Document, document_id).status == DocumentStatus.PENDING
        process_document(session, document_id, provider(), outbox_id=outbox_id)
    assert_complete(document_id, outbox_id)


def test_publisher_cold_start_registers_tasks_without_circular_import():
    program = """
import uuid
from types import SimpleNamespace
from unittest.mock import patch
from app.services.outbox import publish_ingestion
with patch('celery.app.base.Celery.send_task') as send:
    intent = SimpleNamespace(id=uuid.uuid4(), document_id=uuid.uuid4())
    publish_ingestion(intent)
    send.assert_called_once_with(
        'documents.process', args=[str(intent.document_id), str(intent.id)],
        task_id=str(intent.id), retry=False,
    )
from app.core.celery import celery_app
assert 'documents.process' in celery_app.tasks
"""
    result = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
