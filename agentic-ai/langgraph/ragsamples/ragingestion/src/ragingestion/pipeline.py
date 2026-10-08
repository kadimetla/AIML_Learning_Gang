"""Step 3 - EMBED + STORE. Re-ingesting the same file replaces its old chunks (idempotent)."""

import hashlib
from pathlib import Path

from ragstore import delete_source, get_vectorstore

from .chunking import chunk
from .loaders import load_file


def ingest_file(path: Path, *, source_name: str | None = None, collection: str | None = None,
                backend: str | None = None, strategy: str = "recursive", size: int = 800,
                overlap: int = 100) -> dict:
    source = source_name or path.name
    docs = load_file(path, source)
    chunks = chunk(docs, strategy, size, overlap)
    if not chunks:
        raise ValueError(f"No text extracted from {source} (scanned PDF?)")

    vs = get_vectorstore(collection, backend)
    if backend is None:
        delete_source(source, collection)  # drop stale chunks from a previous version
    ids = [hashlib.sha1(f"{source}:{c.metadata['chunk_index']}:{c.page_content}".encode()).hexdigest()
           for c in chunks]
    # Qdrant needs UUID ids; derive a stable uuid from the sha for every backend.
    ids = [f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}" for h in ids]
    vs.add_documents(chunks, ids=ids)
    return {"source": source, "pages": len(docs), "chunks": len(chunks), "strategy": strategy,
            "size": size, "overlap": overlap}
