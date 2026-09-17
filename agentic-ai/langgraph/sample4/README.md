# sample4 — agentic RAG: ingestion + three query-time flows

Two separate concerns, kept in separate files:

- **Ingestion** (`ingestion/ingest_md.py`) — offline, run once. Walks this
  workspace's own `README.md` files, chunks them with
  `MarkdownHeaderTextSplitter` (header-aware, so each chunk keeps its
  section path as metadata) followed by a `RecursiveCharacterTextSplitter`
  size cap, embeds with `OpenAIEmbeddings`, and writes the result into
  **both** a FAISS index and a Chroma collection under `data/`.

  Why not docling here: docling earns its keep on PDFs/DOCX/scanned docs
  (layout detection, table/figure extraction, OCR) — none of that applies
  to plain markdown, which is already structured. If you're ingesting real
  wiki exports with markup instead of `.md`, add a thin markup-stripping
  step before the same header splitter.

  ```bash
  uv run ingestion/ingest_md.py
  ```

- **Query-time flows** (`query_flows/*.py`) — three different ways
  "agentic" gets implemented on top of the *same* indexed data, each
  runnable independently:

  | file | pattern | what decides |
  |---|---|---|
  | `01_retrieval_as_tool.py` | ReAct-style tool calling | the LLM decides, per turn, whether to call `retrieve` at all (same `agent`/`ToolNode`/`tools_condition` loop as `sample3`) |
  | `02_corrective_rag.py` | Corrective RAG | retrieval is unconditional; the graph grades relevance and loops through `rewrite_query` up to `MAX_REWRITES` times before generating |
  | `03_query_routing.py` | Query routing | a router node classifies the question *before* retrieval and picks `repo_docs` (retrieve+generate) or `general` (answer directly), skipping retrieval entirely on that branch |

  ```bash
  uv run query_flows/01_retrieval_as_tool.py
  uv run query_flows/02_corrective_rag.py
  uv run query_flows/03_query_routing.py
  ```

`query_flows/store.py` holds the shared `load_faiss_retriever` /
`load_chroma_retriever` / `format_docs` helpers so each flow file stays
focused on its own graph logic.

Needs `OPENAI_API_KEY` in `.env` (copy `.env.example`) — used for
embeddings directly (`OpenAIEmbeddings`) and for chat completions via
`init_chat_model("litellm:gpt-4o-mini")` routed through litellm, same
pattern as `sample3`.
