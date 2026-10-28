import time
import uuid

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.repositories.documents import semantic_search
from app.services.embeddings import EmbeddingProvider, OpenAIEmbeddingProvider


def search_chunks(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    knowledge_base_id: uuid.UUID,
    query: str,
    top_k: int | None = None,
    provider: EmbeddingProvider | None = None,
) -> tuple[list[dict[str, object]], float]:
    settings = get_settings()
    k = top_k or settings.semantic_search_default_k
    if not 1 <= k <= settings.semantic_search_max_k:
        raise ValueError(
            f"top_k must be between 1 and {settings.semantic_search_max_k}"
        )
    if not query.strip():
        raise ValueError("query must not be empty")
    started = time.perf_counter()
    embedding_provider = provider or OpenAIEmbeddingProvider()
    vector = embedding_provider.embed([query])[0]
    results = semantic_search(
        session,
        workspace_id=workspace_id,
        knowledge_base_id=knowledge_base_id,
        query_vector=vector,
        top_k=k,
    )
    return results, (time.perf_counter() - started) * 1000
