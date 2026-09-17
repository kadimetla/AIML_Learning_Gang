"""Ingestion: walk this workspace's own README.md files, chunk them, embed
them, and write the result into both a FAISS index and a Chroma collection
so the query_flows/ samples can retrieve from either backend.

Why MarkdownHeaderTextSplitter instead of docling: docling earns its keep on
PDFs/DOCX/scanned docs (layout detection, table/figure extraction, OCR) --
none of that applies to plain markdown, which is already structured. This
splitter chunks on '#'/'##'/'###' boundaries and carries the header path
into each chunk's metadata (e.g. {"Header 1": "sample3", "Header 2":
"tool calling with ToolNode"}), which is exactly the structure a
README/wiki corpus already has. A RecursiveCharacterTextSplitter pass
follows it to cap any section that's still too large for one chunk.

Run once before any query_flows/*.py script:
    uv run ingestion/ingest_md.py
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from langchain_chroma import Chroma
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

# Repo root a few levels up from this file -- .../AIML_Learning_Gang/
REPO_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FAISS_DIR = DATA_DIR / "faiss_index"
CHROMA_DIR = DATA_DIR / "chroma_db"

EXCLUDE_DIRS = {".venv", "node_modules", ".git", "__pycache__", ".mypy_cache", ".idea"}

HEADERS_TO_SPLIT_ON = [("#", "Header 1"), ("##", "Header 2"), ("###", "Header 3")]


def find_markdown_files() -> list[Path]:
    paths = []
    for path in REPO_ROOT.rglob("*.md"):
        if EXCLUDE_DIRS.isdisjoint(path.parts):
            paths.append(path)
    return paths


def load_and_split(paths: list[Path]) -> list[Document]:
    header_splitter = MarkdownHeaderTextSplitter(HEADERS_TO_SPLIT_ON, strip_headers=False)
    char_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)

    all_chunks: list[Document] = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
        if not text:
            continue
        source = str(path.relative_to(REPO_ROOT))
        for section in header_splitter.split_text(text):
            for chunk in char_splitter.split_documents([section]):
                chunk.metadata["source"] = source
                all_chunks.append(chunk)
    return all_chunks


def main():
    paths = find_markdown_files()
    print(f"Found {len(paths)} markdown files under {REPO_ROOT}")

    chunks = load_and_split(paths)
    print(f"Split into {len(chunks)} chunks")

    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    faiss_store = FAISS.from_documents(chunks, embeddings)
    faiss_store.save_local(str(FAISS_DIR))
    print(f"Wrote FAISS index -> {FAISS_DIR}")

    Chroma.from_documents(
        chunks,
        embeddings,
        collection_name="repo_docs",
        persist_directory=str(CHROMA_DIR),
    )
    print(f"Wrote Chroma collection 'repo_docs' -> {CHROMA_DIR}")


if __name__ == "__main__":
    main()
