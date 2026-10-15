"""Step 1 - LOAD: turn a file into LangChain Documents via a pluggable loader registry.

Each loader is registered under a name and the extensions it handles. The first loader
registered for an extension is its default; pass `loader="name"` to pick another one.
Add your own with `@register("name", {".ext"})` - heavy imports belong inside the function
so optional dependencies are only needed when that loader is actually used.
"""

from collections.abc import Callable
from pathlib import Path

from langchain_core.documents import Document

Loader = Callable[[Path, str], list[Document]]

_LOADERS: dict[str, tuple[Loader, frozenset[str]]] = {}
_DEFAULTS: dict[str, str] = {}  # extension -> default loader name


def register(name: str, extensions: set[str]):
    def deco(fn: Loader) -> Loader:
        _LOADERS[name] = (fn, frozenset(extensions))
        for ext in extensions:
            _DEFAULTS.setdefault(ext, name)
        return fn

    return deco


def available_loaders() -> dict[str, list[str]]:
    return {name: sorted(exts) for name, (_, exts) in _LOADERS.items()}


def supported_extensions() -> list[str]:
    return sorted(_DEFAULTS)


TEXT_EXT = {".txt", ".md", ".markdown", ".rst", ".csv", ".json", ".py", ".html", ".htm"}


@register("pypdf", {".pdf"})
def _pypdf(path: Path, source: str) -> list[Document]:
    from pypdf import PdfReader

    docs = []
    for i, page in enumerate(PdfReader(str(path)).pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            docs.append(Document(page_content=text, metadata={"source": source, "page": i}))
    return docs


@register("pymupdf4llm", {".pdf"})
def _pymupdf4llm(path: Path, source: str) -> list[Document]:
    """Layout-aware PDF -> Markdown (keeps headings/tables); pair with the `markdown` chunk strategy."""
    import pymupdf4llm

    pages = pymupdf4llm.to_markdown(str(path), page_chunks=True)
    return [
        Document(page_content=p["text"], metadata={"source": source, "page": p["metadata"]["page_number"]})
        for p in pages
        if p["text"].strip()
    ]


@register("text", TEXT_EXT)
def _text(path: Path, source: str) -> list[Document]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return [Document(page_content=text, metadata={"source": source})]


@register("docx", {".docx"})
def _docx(path: Path, source: str) -> list[Document]:
    import docx

    text = "\n\n".join(p.text for p in docx.Document(str(path)).paragraphs if p.text.strip())
    return [Document(page_content=text, metadata={"source": source})]


IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


@register("ocr", IMAGE_EXT | {".pdf"})
def _ocr(path: Path, source: str) -> list[Document]:
    """Tesseract OCR for images and scanned PDFs (needs the `tesseract` binary; PDFs also need poppler)."""
    import pytesseract
    from PIL import Image

    if path.suffix.lower() == ".pdf":
        from pdf2image import convert_from_path

        images = convert_from_path(str(path), dpi=300)
    else:
        images = [Image.open(path)]
    docs = []
    for i, img in enumerate(images, start=1):
        text = pytesseract.image_to_string(img)
        if text.strip():
            meta = {"source": source, "ocr": True}
            if path.suffix.lower() == ".pdf":
                meta["page"] = i
            docs.append(Document(page_content=text, metadata=meta))
    return docs


@register("docling", {".pdf", ".docx", ".pptx", ".html", ".htm", ".md"} | IMAGE_EXT)
def _docling(path: Path, source: str) -> list[Document]:
    """Docling: layout analysis + tables + built-in OCR -> Markdown, one Document per page when paged."""
    from docling.document_converter import DocumentConverter

    doc = DocumentConverter().convert(str(path)).document
    pages = sorted(doc.pages) if doc.pages else []
    if len(pages) > 1:
        out = [(n, doc.export_to_markdown(page_no=n)) for n in pages]
        return [Document(page_content=t, metadata={"source": source, "page": n}) for n, t in out if t.strip()]
    text = doc.export_to_markdown()
    return [Document(page_content=text, metadata={"source": source})] if text.strip() else []


def load_file(path: Path, source_name: str | None = None, loader: str | None = None) -> list[Document]:
    source = source_name or path.name
    ext = path.suffix.lower()
    if loader is None:
        loader = _DEFAULTS.get(ext)
        if loader is None:
            raise ValueError(f"Unsupported file type {ext!r}. Supported: {' '.join(supported_extensions())}")
    elif loader not in _LOADERS:
        raise ValueError(f"Unknown loader {loader!r}; choose from {list(_LOADERS)}")
    fn, exts = _LOADERS[loader]
    if ext not in exts:
        raise ValueError(f"Loader {loader!r} does not handle {ext!r} (handles {sorted(exts)})")
    docs = fn(path, source)
    if not docs and loader == _DEFAULTS.get(ext) and ext == ".pdf":
        docs = _ocr(path, source)  # no text layer -> scanned PDF, fall back to OCR
    return docs
