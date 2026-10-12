from io import BytesIO

from docx import Document as DocxDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}

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