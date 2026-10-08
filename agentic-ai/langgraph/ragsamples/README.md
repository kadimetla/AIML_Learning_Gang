# ragsamples — agentic RAG, split into ingestion and query

```
ragstore/      shared: settings, embeddings, vector-store factory (chroma | qdrant | pgvector)
ragingestion/  load -> chunk -> embed -> store     (CLI `ragingest` + upload API :8001)
ragquery/      LangGraph agent: route -> retrieve -> grade -> rewrite -> answer (API :8002, serves UI)
ui/index.html  chat + upload + document list
```

Ingestion and query are separate projects that only share the vector store (via `ragstore`).
Switch backends with `VECTOR_BACKEND` in `.env`; no code changes.

## Run
```bash
cp .env.example .env            # add OPENAI_API_KEY
(cd ragingestion && uv run ragingestion-api)    # terminal 1  -> :8001
(cd ragquery     && uv run ragquery-api)        # terminal 2  -> :8002
open http://127.0.0.1:8002                      # chat UI
```
CLI: `cd ragingestion && uv run ragingest ../some.pdf --strategy recursive --size 800`
and `cd ragquery && uv run ragask "question"`.

## Other backends
`docker compose up -d`, then set `VECTOR_BACKEND=qdrant` + `QDRANT_URL=http://localhost:6333`
or `VECTOR_BACKEND=pgvector`. (Embedded qdrant/chroma on disk is single-process; with
two services use chroma, or a Qdrant/Postgres server.)

## Agent graph
route (needs docs?) → retrieve top-k → grade each chunk → if none relevant, rewrite query
and retry (max 2) → answer with [n] citations, or say it could not find it.

## Tested
chroma, qdrant (docker server) and pgvector (docker) all pass: ingest, query with citations,
re-ingest without duplicates, list and delete. Environment variables override `.env`, e.g.
`VECTOR_BACKEND=pgvector uv run ragask "..."`.
