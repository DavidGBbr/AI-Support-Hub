import uuid

import pytest

from app.services.search import search_chunks


class FakeEmbeddingProvider:
    def embed(self, texts: list[str]) -> list[list[float]]:
        assert len(texts) == 1
        return [[1.0, 0.0, 0.0]]


def test_search_forwards_workspace_and_knowledge_base_filters(monkeypatch) -> None:
    workspace_id = uuid.uuid4()
    knowledge_base_id = uuid.uuid4()
    document_id = uuid.uuid4()
    captured: dict[str, object] = {}

    def fake_semantic_search(session, **kwargs):
        captured.update(kwargs)
        return [
            {
                "document_id": document_id,
                "content": "O prazo para reembolso é de sete dias.",
                "score": 0.97,
            }
        ]

    monkeypatch.setattr("app.services.search.semantic_search", fake_semantic_search)

    results, duration_ms = search_chunks(
        object(),
        workspace_id=workspace_id,
        knowledge_base_id=knowledge_base_id,
        query="Qual é o prazo para reembolso?",
        top_k=3,
        provider=FakeEmbeddingProvider(),
    )

    assert captured["workspace_id"] == workspace_id
    assert captured["knowledge_base_id"] == knowledge_base_id
    assert captured["top_k"] == 3
    assert results[0]["document_id"] == document_id
    assert results[0]["score"] == pytest.approx(0.97)
    assert duration_ms >= 0


def test_search_rejects_empty_query() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        search_chunks(
            object(),
            workspace_id=uuid.uuid4(),
            knowledge_base_id=uuid.uuid4(),
            query="   ",
            provider=FakeEmbeddingProvider(),
        )
