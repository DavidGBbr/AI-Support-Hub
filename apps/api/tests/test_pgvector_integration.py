import uuid
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models.domain import (
    Document,
    DocumentChunk,
    DocumentStatus,
    KnowledgeBase,
    Workspace,
)
from app.repositories.documents import semantic_search
from app.services.ingestion import process_document

pytestmark = pytest.mark.pgvector


def _vector(axis: int) -> list[float]:
    values = [0.0] * get_settings().embedding_dimensions
    values[axis] = 1.0
    return values


class ConstantEmbeddingProvider:
    def __init__(self, vector: list[float]) -> None:
        self.vector = vector

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.vector.copy() for _ in texts]


@pytest.fixture
def db_session() -> Session:
    session = SessionLocal()
    try:
        session.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
    except Exception as exc:
        session.close()
        pytest.skip(f"PostgreSQL/pgvector integration database unavailable: {exc}")

    workspace_ids: list[uuid.UUID] = []
    session._test_workspace_ids = workspace_ids
    try:
        yield session
    finally:
        session.rollback()
        for workspace_id in workspace_ids:
            session.execute(delete(Workspace).where(Workspace.id == workspace_id))
        session.commit()
        session.close()


def _workspace_with_kb(session: Session, name: str) -> tuple[Workspace, KnowledgeBase]:
    workspace = Workspace(name=name)
    session.add(workspace)
    session.flush()
    kb = KnowledgeBase(workspace_id=workspace.id, name=f"{name} KB")
    session.add(kb)
    session.flush()
    session._test_workspace_ids.append(workspace.id)  # type: ignore[attr-defined]
    return workspace, kb


def _ready_document(
    session: Session,
    *,
    workspace: Workspace,
    kb: KnowledgeBase,
    filename: str,
) -> Document:
    document = Document(
        workspace_id=workspace.id,
        knowledge_base_id=kb.id,
        filename=filename,
        content_type="text/plain",
        storage_path=f"/tmp/{filename}",
        size_bytes=1,
        status=DocumentStatus.READY,
    )
    session.add(document)
    session.flush()
    return document


def _chunk(
    session: Session,
    *,
    document: Document,
    content: str,
    vector: list[float],
    position: int = 0,
) -> None:
    session.add(
        DocumentChunk(
            workspace_id=document.workspace_id,
            knowledge_base_id=document.knowledge_base_id,
            document_id=document.id,
            position=position,
            content=content,
            token_count=5,
            embedding=vector,
        )
    )


def test_top_k_returns_most_similar_chunks_with_document_content_and_score(
    db_session: Session,
) -> None:
    workspace, kb = _workspace_with_kb(db_session, "Top K")
    relevant = _ready_document(
        db_session, workspace=workspace, kb=kb, filename="refund.txt"
    )
    unrelated = _ready_document(
        db_session, workspace=workspace, kb=kb, filename="shipping.txt"
    )
    _chunk(
        db_session,
        document=relevant,
        content="O prazo para solicitar reembolso é de sete dias.",
        vector=_vector(0),
    )
    _chunk(
        db_session,
        document=unrelated,
        content="As entregas são realizadas em dias úteis.",
        vector=_vector(1),
    )
    db_session.commit()

    results = semantic_search(
        db_session,
        workspace_id=workspace.id,
        knowledge_base_id=kb.id,
        query_vector=_vector(0),
        top_k=1,
    )

    assert len(results) == 1
    assert results[0]["document_id"] == relevant.id
    assert results[0]["content"] == "O prazo para solicitar reembolso é de sete dias."
    assert float(results[0]["score"]) == pytest.approx(1.0)


def test_search_isolates_workspace_and_knowledge_base(db_session: Session) -> None:
    workspace_a, kb_a = _workspace_with_kb(db_session, "Workspace A")
    workspace_b, kb_b = _workspace_with_kb(db_session, "Workspace B")
    kb_a_other = KnowledgeBase(workspace_id=workspace_a.id, name="Workspace A Other KB")
    db_session.add(kb_a_other)
    db_session.flush()

    doc_a = _ready_document(
        db_session, workspace=workspace_a, kb=kb_a, filename="a.txt"
    )
    doc_b = _ready_document(
        db_session, workspace=workspace_b, kb=kb_b, filename="b.txt"
    )
    doc_other_kb = _ready_document(
        db_session, workspace=workspace_a, kb=kb_a_other, filename="other-kb.txt"
    )
    for document, content in (
        (doc_a, "conteúdo permitido"),
        (doc_b, "conteúdo de outro workspace"),
        (doc_other_kb, "conteúdo de outra knowledge base"),
    ):
        _chunk(db_session, document=document, content=content, vector=_vector(0))
    db_session.commit()

    results = semantic_search(
        db_session,
        workspace_id=workspace_a.id,
        knowledge_base_id=kb_a.id,
        query_vector=_vector(0),
        top_k=10,
    )

    assert [row["document_id"] for row in results] == [doc_a.id]
    assert all(row["document_id"] != doc_b.id for row in results)
    assert all(row["document_id"] != doc_other_kb.id for row in results)


def test_search_ignores_chunks_from_non_ready_documents(db_session: Session) -> None:
    workspace, kb = _workspace_with_kb(db_session, "Status Filter")
    ready = _ready_document(
        db_session, workspace=workspace, kb=kb, filename="ready.txt"
    )
    failed = _ready_document(
        db_session, workspace=workspace, kb=kb, filename="failed.txt"
    )
    failed.status = DocumentStatus.FAILED
    _chunk(db_session, document=ready, content="ready", vector=_vector(0))
    _chunk(db_session, document=failed, content="failed", vector=_vector(0))
    db_session.commit()

    results = semantic_search(
        db_session,
        workspace_id=workspace.id,
        knowledge_base_id=kb.id,
        query_vector=_vector(0),
        top_k=10,
    )

    assert [row["document_id"] for row in results] == [ready.id]


def test_reprocessing_replaces_chunks_without_duplicates(
    db_session: Session, tmp_path: Path
) -> None:
    workspace, kb = _workspace_with_kb(db_session, "Reprocessing")
    path = tmp_path / "policy.txt"
    path.write_text("Versão inicial da política de reembolso.", encoding="utf-8")
    document = Document(
        workspace_id=workspace.id,
        knowledge_base_id=kb.id,
        filename=path.name,
        content_type="text/plain",
        storage_path=str(path),
        size_bytes=path.stat().st_size,
        status=DocumentStatus.PENDING,
    )
    db_session.add(document)
    db_session.commit()

    provider = ConstantEmbeddingProvider(_vector(0))
    process_document(db_session, document.id, provider=provider)
    first_count = db_session.scalar(
        select(func.count())
        .select_from(DocumentChunk)
        .where(DocumentChunk.document_id == document.id)
    )

    path.write_text(
        "Versão atualizada: o reembolso ocorre em sete dias.", encoding="utf-8"
    )
    process_document(db_session, document.id, provider=provider)
    chunks = db_session.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.position)
    ).all()

    assert first_count == 1
    assert len(chunks) == 1
    assert "Versão atualizada" in chunks[0].content
    assert db_session.get(Document, document.id).status == DocumentStatus.READY
