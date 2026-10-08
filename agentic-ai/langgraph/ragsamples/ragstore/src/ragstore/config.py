"""All settings come from environment variables (.env at the ragsamples root)."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]  # .../ragsamples
load_dotenv(ROOT / ".env")


def _path(value: str) -> str:
    p = Path(value)
    return str(p if p.is_absolute() else ROOT / p)


@dataclass(frozen=True)
class Settings:
    embed_model: str = os.getenv("EMBED_MODEL", "text-embedding-3-small")
    chat_model: str = os.getenv("CHAT_MODEL", "gpt-4o-mini")
    backend: str = os.getenv("VECTOR_BACKEND", "chroma").lower()
    collection: str = os.getenv("COLLECTION", "documents")
    chroma_dir: str = _path(os.getenv("CHROMA_DIR", "./data/chroma"))
    qdrant_url: str = os.getenv("QDRANT_URL", "")
    qdrant_path: str = _path(os.getenv("QDRANT_PATH", "./data/qdrant"))
    pg_conn: str = os.getenv("PG_CONN", "postgresql+psycopg://rag:rag@localhost:5432/rag")
    ingest_port: int = int(os.getenv("INGEST_PORT", "8001"))
    query_port: int = int(os.getenv("QUERY_PORT", "8002"))


settings = Settings()
