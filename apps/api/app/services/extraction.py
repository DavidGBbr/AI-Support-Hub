from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PyPdfError

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 100
SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md", ".markdown"}


class DocumentExtractionError(ValueError):
    pass


@dataclass(frozen=True)
class ExtractedDocument:
    text: str
    page_count: int | None = None


def _useful(text: str) -> str:
    normalized = "\n".join(
        line.strip() for line in text.splitlines() if line.strip()
    ).strip()
    if not normalized:
        raise DocumentExtractionError("document has no useful textual content")
    return normalized


def extract_text(path: str | Path) -> ExtractedDocument:
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        raise DocumentExtractionError("document file is unavailable")
    if file_path.stat().st_size > MAX_FILE_BYTES:
        raise DocumentExtractionError("document exceeds the 10 MiB limit")
    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise DocumentExtractionError("unsupported document type")

    try:
        if suffix == ".pdf":
            reader = PdfReader(str(file_path))
            if len(reader.pages) > MAX_PDF_PAGES:
                raise DocumentExtractionError("PDF exceeds the 100 page limit")
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            return ExtractedDocument(_useful(text), len(reader.pages))
        return ExtractedDocument(_useful(file_path.read_text(encoding="utf-8")))
    except DocumentExtractionError:
        raise
    except (OSError, UnicodeError, ValueError, PyPdfError) as exc:
        raise DocumentExtractionError("document could not be read safely") from exc
