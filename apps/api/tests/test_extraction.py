from pathlib import Path

import pytest

from app.services.extraction import DocumentExtractionError, extract_text


def test_extracts_txt(tmp_path: Path) -> None:
    path = tmp_path / "policy.txt"
    path.write_text("Prazo de reembolso: 7 dias.", encoding="utf-8")
    assert "7 dias" in extract_text(path).text


def test_extracts_markdown(tmp_path: Path) -> None:
    path = tmp_path / "policy.md"
    path.write_text("# Política\n\nReembolso em 7 dias.", encoding="utf-8")
    assert "Política" in extract_text(path).text


def test_rejects_empty_document(tmp_path: Path) -> None:
    path = tmp_path / "empty.txt"
    path.write_text("  \n", encoding="utf-8")
    with pytest.raises(DocumentExtractionError):
        extract_text(path)


def test_extracts_pdf_text() -> None:
    fixture = Path(__file__).parent / "fixtures" / "policy.pdf"
    extracted = extract_text(fixture)
    assert extracted.page_count == 1
    assert "7 dias" in extracted.text


def test_rejects_document_above_10_mib(tmp_path: Path) -> None:
    path = tmp_path / "too-large.txt"
    with path.open("wb") as file:
        file.seek(10 * 1024 * 1024)
        file.write(b"x")
    with pytest.raises(DocumentExtractionError, match="10 MiB"):
        extract_text(path)


def test_rejects_pdf_above_100_pages(tmp_path: Path) -> None:
    from pypdf import PdfWriter

    path = tmp_path / "too-many-pages.pdf"
    writer = PdfWriter()
    for _ in range(101):
        writer.add_blank_page(width=72, height=72)
    with path.open("wb") as file:
        writer.write(file)

    with pytest.raises(DocumentExtractionError, match="100 page"):
        extract_text(path)


def test_rejects_unsupported_document_type(tmp_path: Path) -> None:
    path = tmp_path / "policy.docx"
    path.write_bytes(b"not a supported document")
    with pytest.raises(DocumentExtractionError, match="unsupported"):
        extract_text(path)


def test_rejects_corrupted_pdf(tmp_path: Path) -> None:
    path = tmp_path / "corrupted.pdf"
    path.write_bytes(b"this is not a pdf")
    with pytest.raises(DocumentExtractionError, match="could not be read safely"):
        extract_text(path)
