"""Load the FAISS/Chroma indexes built by ingestion/ingest_md.py. Each
query_flows/*.py sample imports one of these rather than re-embedding
anything -- ingestion and query time are separate steps.
"""

from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FAISS_DIR = DATA_DIR / "faiss_index"
CHROMA_DIR = DATA_DIR / "chroma_db"

_embeddings = OpenAIEmbeddings(model="text-embedding-3-small")


def load_faiss_retriever(k: int = 4):
    if not FAISS_DIR.exists():
        raise FileNotFoundError(
            f"{FAISS_DIR} not found -- run `uv run ingestion/ingest_md.py` first."
        )
    store = FAISS.load_local(
        str(FAISS_DIR), _embeddings, allow_dangerous_deserialization=True
    )
    return store.as_retriever(search_kwargs={"k": k})


def load_chroma_retriever(k: int = 4):
    if not CHROMA_DIR.exists():
        raise FileNotFoundError(
            f"{CHROMA_DIR} not found -- run `uv run ingestion/ingest_md.py` first."
        )
    store = Chroma(
        collection_name="repo_docs",
        embedding_function=_embeddings,
        persist_directory=str(CHROMA_DIR),
    )
    return store.as_retriever(search_kwargs={"k": k})


def format_docs(docs) -> str:
    parts = []
    for doc in docs:
        header = " > ".join(
            v for k, v in doc.metadata.items() if k.startswith("Header") and v
        )
        source = doc.metadata.get("source", "unknown")
        label = f"{source}" + (f" ({header})" if header else "")
        parts.append(f"[{label}]\n{doc.page_content}")
    return "\n\n---\n\n".join(parts)
