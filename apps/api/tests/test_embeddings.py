from app.services.chunking import TextChunk


class FakeEmbeddingProvider:
    def __init__(self, dimensions: int = 3) -> None:
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 0.5, 1.0] for text in texts]


def test_fake_provider_keeps_one_vector_per_input() -> None:
    provider = FakeEmbeddingProvider()
    chunks = [TextChunk(0, "um", 1), TextChunk(1, "dois", 1)]
    vectors = provider.embed([chunk.content for chunk in chunks])
    assert len(vectors) == 2
    assert all(len(vector) == 3 for vector in vectors)
