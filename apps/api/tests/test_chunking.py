from app.services.chunking import chunk_text


def test_chunking_is_deterministic() -> None:
    text = "Política de reembolso. " * 300
    first = chunk_text(text, chunk_size=80, overlap=10)
    second = chunk_text(text, chunk_size=80, overlap=10)
    assert first == second
    assert [chunk.position for chunk in first] == list(range(len(first)))
    assert all(chunk.token_count <= 80 for chunk in first)


def test_chunking_rejects_invalid_overlap() -> None:
    try:
        chunk_text("texto", chunk_size=10, overlap=10)
    except ValueError as exc:
        assert "overlap" in str(exc)
    else:
        raise AssertionError("expected ValueError")
