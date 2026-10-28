from dataclasses import dataclass

import tiktoken

from app.core.config import get_settings


@dataclass(frozen=True)
class TextChunk:
    position: int
    content: str
    token_count: int


def chunk_text(
    text: str,
    *,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[TextChunk]:
    settings = get_settings()
    size = chunk_size or settings.chunk_size
    shared = settings.chunk_overlap if overlap is None else overlap
    if size <= 0 or shared < 0 or shared >= size:
        raise ValueError(
            "chunk_size must be positive and overlap must be >= 0 and < chunk_size"
        )

    encoding = tiktoken.get_encoding("cl100k_base")
    tokens = encoding.encode(text)
    if not tokens:
        return []

    chunks: list[TextChunk] = []
    step = size - shared
    for position, start in enumerate(range(0, len(tokens), step)):
        part = tokens[start : start + size]
        if not part:
            break
        chunks.append(
            TextChunk(
                position=position,
                content=encoding.decode(part).strip(),
                token_count=len(part),
            )
        )
        if start + size >= len(tokens):
            break
    return chunks
