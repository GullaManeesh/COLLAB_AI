from io import BytesIO
import logging
from typing import BinaryIO, Iterator

from docx import Document as DocxDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from app.services.memory_diagnostics import rss_log_value


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def extract_text(filename: str, file_bytes: bytes) -> list[dict]:
    """
    Return extracted text with page metadata.

    Each item has:
        text: extracted text
        page: page number, or None for non-paginated files
    """
    filename_lower = filename.lower()

    if not file_bytes:
        raise ValueError("The uploaded file is empty")

    if len(file_bytes) > MAX_FILE_SIZE:
        raise ValueError("File exceeds the 10 MB size limit")

    if filename_lower.endswith(".pdf"):
        reader = PdfReader(BytesIO(file_bytes))

        if reader.is_encrypted:
            raise ValueError("Password-protected PDFs are not supported")

        pages = []

        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""

            if text.strip():
                pages.append({
                    "text": text,
                    "page": page_number,
                })

        return pages

    if filename_lower.endswith(".docx"):
        document = DocxDocument(BytesIO(file_bytes))
        parts = []

        # Extract regular paragraphs
        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if text:
                parts.append(text)

        # Extract all tables without omitting tabular data
        for table in document.tables:
            for row in table.rows:
                row_cells = []
                for cell in row.cells:
                    cell_text = cell.text.strip()
                    if cell_text and (not row_cells or row_cells[-1] != cell_text):
                        row_cells.append(cell_text)
                if row_cells:
                    parts.append(" | ".join(row_cells))

        text = "\n\n".join(parts)
        return [{"text": text, "page": None}] if text.strip() else []

    if filename_lower.endswith((".txt", ".md")):
        try:
            text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = file_bytes.decode("latin-1")
            except Exception:
                text = file_bytes.decode("utf-8", errors="replace")

        return [{"text": text.strip(), "page": None}] if text.strip() else []

    raise ValueError(
        "Unsupported file type. Upload PDF, DOCX, TXT, or Markdown."
    )


def iter_document_chunks(
    filename: str,
    file_bytes: bytes | BinaryIO,
    file_size: int | None = None,
    diagnostic_id: str | None = None,
) -> Iterator[dict]:
    """Extract and chunk one PDF page at a time to bound ingestion memory."""
    filename_lower = filename.lower()

    if isinstance(file_bytes, bytes):
        actual_size = len(file_bytes)
    elif file_size is None:
        file_bytes.seek(0, 2)
        actual_size = file_bytes.tell()
        file_bytes.seek(0)
    else:
        actual_size = file_size

    if actual_size == 0:
        raise ValueError("The uploaded file is empty")
    if actual_size > MAX_FILE_SIZE:
        raise ValueError("File exceeds the 10 MB size limit")
    if not filename_lower.endswith((".pdf", ".docx", ".txt", ".md")):
        raise ValueError("Unsupported file type. Upload PDF, DOCX, TXT, or Markdown.")

    if filename_lower.endswith(".pdf"):
        pdf_stream = BytesIO(file_bytes) if isinstance(file_bytes, bytes) else file_bytes
        pdf_stream.seek(0)
        reader = PdfReader(pdf_stream)
        if reader.is_encrypted:
            raise ValueError("Password-protected PDFs are not supported")

        def extract_pdf_pages():
            for page_number, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                logger.info(
                    "Document PDF page extracted document_id=%s page=%d extracted_characters=%d rss_mb=%s",
                    diagnostic_id or "unknown",
                    page_number,
                    len(text),
                    rss_log_value(),
                )
                yield {"text": text, "page": page_number}

        pages = extract_pdf_pages()
    else:
        if isinstance(file_bytes, bytes):
            content_bytes = file_bytes
        else:
            file_bytes.seek(0)
            content_bytes = file_bytes.read(MAX_FILE_SIZE + 1)
            file_bytes.seek(0)
        pages = iter(extract_text(filename, content_bytes))

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150,
        separators=["\n\n", "\n", ". ", " ", ""],
        add_start_index=True,
    )

    for page_data in pages:
        text = page_data["text"]
        if not text.strip():
            continue

        page_number = page_data.get("page")
        page_characters = len(text)
        logger.info(
            "Document page chunking started document_id=%s page=%s source_characters=%d rss_mb=%s",
            diagnostic_id or "unknown",
            page_number if page_number is not None else "none",
            page_characters,
            rss_log_value(),
        )
        page_chunks = splitter.create_documents([text])
        logger.info(
            "Document page chunking completed document_id=%s page=%s chunk_count=%d rss_mb=%s",
            diagnostic_id or "unknown",
            page_number if page_number is not None else "none",
            len(page_chunks),
            rss_log_value(),
        )
        for chunk in page_chunks:
            chunk_text_value = chunk.page_content.strip()
            if not chunk_text_value:
                continue
            yield {
                "text": chunk_text_value,
                "page": page_number,
                "start_index": chunk.metadata.get("start_index", 0),
                # Count each page's source text once, not its overlapping chunks.
                "_extracted_characters": page_characters,
            }
            page_characters = 0
        del page_chunks, text, page_data


def chunk_text(
    extracted_pages: list[dict],
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
) -> list[dict]:
    """
    Split extracted text into overlapping chunks.

    Retain the source page number where available.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
        add_start_index=True,
    )

    chunks = []

    for page_data in extracted_pages:
        text = page_data["text"]
        page_number = page_data.get("page")

        for chunk in splitter.create_documents([text]):
            chunk_text_value = chunk.page_content.strip()

            if not chunk_text_value:
                continue

            chunks.append({
                "text": chunk_text_value,
                "page": page_number,
                "start_index": chunk.metadata.get("start_index", 0),
            })

    return chunks
