"""Step 1 - LOAD: turn a file into LangChain Documents (one per PDF page, else one per file)."""

from pathlib import Path

from langchain_core.documents import Document

TEXT_EXT = {".txt", ".md", ".markdown", ".rst", ".csv", ".json", ".py", ".html", ".htm"}


def load_file(path: Path, source_name: str | None = None) -> list[Document]:
    source = source_name or path.name
    ext = path.suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader

        docs = []
        for i, page in enumerate(PdfReader(str(path)).pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                docs.append(Document(page_content=text, metadata={"source": source, "page": i}))
        return docs
    if ext in TEXT_EXT:
        text = path.read_text(encoding="utf-8", errors="replace")
        return [Document(page_content=text, metadata={"source": source})]
    raise ValueError(f"Unsupported file type {ext!r}. Supported: .pdf {' '.join(sorted(TEXT_EXT))}")
