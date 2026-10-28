import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.models.domain import DocumentStatus
from app.services.chunking import TextChunk
from app.services.extraction import ExtractedDocument
from app.services.ingestion import SAFE_FAILURE_MESSAGE, process_document


class FakeEmbeddingProvider:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]


class FailingEmbeddingProvider:
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("provider unavailable; secret=must-not-be-persisted")


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _document() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        knowledge_base_id=uuid.uuid4(),
        storage_path=Path("policy.txt"),
        status=DocumentStatus.PENDING,
        failure_reason=None,
    )


def test_process_document_marks_ready_only_after_chunks_are_replaced(
    monkeypatch,
) -> None:
    document = _document()
    session = FakeSession()
    statuses: list[DocumentStatus] = []
    replace = Mock()

    monkeypatch.setattr("app.services.ingestion.get_document", lambda *_: document)
    monkeypatch.setattr(
        "app.services.ingestion.extract_text",
        lambda *_: ExtractedDocument("Política de reembolso em sete dias."),
    )
    monkeypatch.setattr(
        "app.services.ingestion.chunk_text",
        lambda *_: [TextChunk(0, "Política de reembolso em sete dias.", 8)],
    )
    monkeypatch.setattr("app.services.ingestion.replace_chunks", replace)

    def mark_status(_session, doc, status, reason=None):
        statuses.append(status)
        doc.status = status
        doc.failure_reason = reason

    monkeypatch.setattr("app.services.ingestion.mark_status", mark_status)

    process_document(session, document.id, provider=FakeEmbeddingProvider())

    assert statuses == [DocumentStatus.PROCESSING, DocumentStatus.READY]
    replace.assert_called_once()
    assert session.commits == 2
    assert session.rollbacks == 0
    assert document.failure_reason is None


def test_process_document_failure_is_safe_and_does_not_replace_chunks(
    monkeypatch,
) -> None:
    document = _document()
    session = FakeSession()
    replace = Mock()

    monkeypatch.setattr("app.services.ingestion.get_document", lambda *_: document)
    monkeypatch.setattr(
        "app.services.ingestion.extract_text",
        lambda *_: ExtractedDocument("Conteúdo válido."),
    )
    monkeypatch.setattr(
        "app.services.ingestion.chunk_text",
        lambda *_: [TextChunk(0, "Conteúdo válido.", 4)],
    )
    monkeypatch.setattr("app.services.ingestion.replace_chunks", replace)

    def mark_status(_session, doc, status, reason=None):
        doc.status = status
        doc.failure_reason = reason

    monkeypatch.setattr("app.services.ingestion.mark_status", mark_status)

    with pytest.raises(RuntimeError, match="provider unavailable"):
        process_document(session, document.id, provider=FailingEmbeddingProvider())

    replace.assert_not_called()
    assert session.rollbacks == 1
    assert session.commits == 2  # PROCESSING and then FAILED
    assert document.status == DocumentStatus.FAILED
    assert document.failure_reason == SAFE_FAILURE_MESSAGE
    assert "secret" not in document.failure_reason
