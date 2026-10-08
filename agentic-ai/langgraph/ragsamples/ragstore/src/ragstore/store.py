"""One factory, three backends. Everything returns a LangChain VectorStore, so the
ingestion and query projects never touch backend-specific code."""

from functools import lru_cache

from langchain_core.vectorstores import VectorStore
from langchain_openai import OpenAIEmbeddings

from .config import settings


@lru_cache
def get_embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(model=settings.embed_model)


@lru_cache
def _qdrant_client():
    from qdrant_client import QdrantClient

    if settings.qdrant_url:
        return QdrantClient(url=settings.qdrant_url)
    return QdrantClient(path=settings.qdrant_path)  # embedded, single process only


@lru_cache
def _chroma_client():
    import chromadb

    return chromadb.PersistentClient(path=settings.chroma_dir)


def get_vectorstore(collection: str | None = None, backend: str | None = None) -> VectorStore:
    collection = collection or settings.collection
    backend = (backend or settings.backend).lower()
    emb = get_embeddings()

    if backend == "chroma":
        from langchain_chroma import Chroma

        return Chroma(collection_name=collection, embedding_function=emb, client=_chroma_client())

    if backend == "qdrant":
        from langchain_qdrant import QdrantVectorStore
        from qdrant_client.models import Distance, VectorParams

        client = _qdrant_client()
        if not client.collection_exists(collection):
            dim = len(emb.embed_query("dimension probe"))
            client.create_collection(collection, vectors_config=VectorParams(size=dim, distance=Distance.COSINE))
        return QdrantVectorStore(client=client, collection_name=collection, embedding=emb)

    if backend == "pgvector":
        from langchain_postgres import PGVector

        return PGVector(embeddings=emb, collection_name=collection, connection=settings.pg_conn, use_jsonb=True)

    raise ValueError(f"Unknown VECTOR_BACKEND {backend!r} (chroma | qdrant | pgvector)")


# ---- document-level helpers (work on metadata["source"]) -------------------

def _all_metadatas(vs: VectorStore) -> list[dict]:
    """Backend-specific scan of stored chunk metadata (fine at learning scale)."""
    name = type(vs).__name__
    if name == "Chroma":
        return vs.get(include=["metadatas"])["metadatas"]
    if name == "QdrantVectorStore":
        out, offset = [], None
        while True:
            pts, offset = vs.client.scroll(vs.collection_name, limit=256, offset=offset, with_payload=True)
            out += [(p.payload or {}).get("metadata", {}) for p in pts]
            if offset is None:
                return out
    if name == "PGVector":
        from sqlalchemy import text

        with vs._make_sync_session() as s:  # noqa: SLF001
            rows = s.execute(text("select e.cmetadata from langchain_pg_embedding e join langchain_pg_collection c "
                                  "on e.collection_id=c.uuid where c.name=:n"), {"n": vs.collection_name})
            return [r[0] for r in rows]
    raise NotImplementedError(name)


def list_sources(collection: str | None = None) -> list[dict]:
    counts: dict[str, int] = {}
    for m in _all_metadatas(get_vectorstore(collection)):
        counts[m.get("source", "?")] = counts.get(m.get("source", "?"), 0) + 1
    return [{"source": s, "chunks": n} for s, n in sorted(counts.items())]


def delete_source(source: str, collection: str | None = None) -> None:
    vs = get_vectorstore(collection)
    name = type(vs).__name__
    if name == "Chroma":
        vs.delete(where={"source": source})
    elif name == "QdrantVectorStore":
        from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

        flt = Filter(must=[FieldCondition(key="metadata.source", match=MatchValue(value=source))])
        vs.client.delete(vs.collection_name, points_selector=FilterSelector(filter=flt))
    elif name == "PGVector":
        from sqlalchemy import text

        with vs._make_sync_session() as s:  # noqa: SLF001
            s.execute(text("delete from langchain_pg_embedding where cmetadata->>'source'=:s and collection_id="
                                  "(select uuid from langchain_pg_collection where name=:n)"),
                      {"s": source, "n": vs.collection_name})
            s.commit()
