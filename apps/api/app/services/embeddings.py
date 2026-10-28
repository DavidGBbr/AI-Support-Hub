from typing import Protocol

from openai import OpenAI

from app.core.config import get_settings


class EmbeddingError(RuntimeError):
    pass


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbeddingProvider:
    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.embedding_model
        self.dimensions = settings.embedding_dimensions
        self.client = OpenAI(api_key=settings.openai_api_key)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=texts,
                encoding_format="float",
                dimensions=self.dimensions,
            )
        except Exception as exc:
            raise EmbeddingError("embedding provider request failed") from exc
        vectors = [
            item.embedding
            for item in sorted(response.data, key=lambda item: item.index)
        ]
        if len(vectors) != len(texts) or any(
            len(v) != self.dimensions for v in vectors
        ):
            raise EmbeddingError(
                "embedding provider returned an unexpected vector shape"
            )
        return vectors
