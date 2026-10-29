"""Where the graph keeps things: Postgres for both persistence objects (docs/MEMORY.md).

  checkpointer  every step of every thread: messages, plan, approval pauses  (working memory)
  store         episodes and workflow traces across threads, by tenant       (long-term memory)

    docker compose up -d            # pgvector/pgvector:pg17 on 127.0.0.1:5434
    DATABASE_URL=postgresql://provisioner:provisioner@127.0.0.1:5434/provisioner

The cloud's own state (what exists) stays in inventory.db: that is the provider's state file,
not agent memory.
"""

import os
from contextlib import asynccontextmanager, contextmanager
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from langchain_litellm import LiteLLMEmbeddings
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import AsyncPostgresStore, PostgresStore

import memory


def database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set: `docker compose up -d`, then copy it from .env.example")
    return url


# The Store's vector search is `WHERE prefix ... ORDER BY embedding <=> q LIMIT n` over an HNSW
# index. Without this, pgvector takes the nearest hnsw.ef_search (40) candidates across ALL tenants
# and filters afterwards, so a small tenant can get fewer cases than exist, or none. With it, the
# index scan keeps going until enough rows pass the filter (pgvector >= 0.8). relaxed_order is
# enough: the Store re-sorts the results by score.
STORE_SESSION = {"hnsw.iterative_scan": "relaxed_order"}


def with_settings(url: str, settings: dict[str, str]) -> str:
    """The URL with `-c name=value` session settings added to libpq's `options` parameter."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query["options"] = " ".join([query.get("options", ""), *(f"-c {k}={v}" for k, v in settings.items())]).strip()
    return urlunsplit(parts._replace(query=urlencode(query, quote_via=quote)))  # %20: libpq does not read "+" as a space


def index_config(embed=None) -> dict:
    """Semantic search for the Store. Only the fields named in memory.INDEXED are embedded
    (an episode's summary, a trace's query), never whole records."""
    return {"dims": int(os.getenv("EMBED_DIMS", "1536")),
            "embed": embed or LiteLLMEmbeddings(model=os.getenv("EMBED_MODEL", "text-embedding-3-small")),
            "fields": memory.INDEXED}


@asynccontextmanager
async def open_async(url: str | None = None, embed=None):
    """server.py: one checkpointer and one store for the process, tables created if missing."""
    url = url or database_url()
    async with (AsyncPostgresSaver.from_conn_string(url) as saver,
                AsyncPostgresStore.from_conn_string(with_settings(url, STORE_SESSION), index=index_config(embed)) as store):
        await saver.setup()
        await store.setup()
        yield saver, store


@contextmanager
def open_sync(url: str | None = None, embed=None):
    """cli.py and tests: the same, without an event loop."""
    url = url or database_url()
    with (PostgresSaver.from_conn_string(url) as saver,
          PostgresStore.from_conn_string(with_settings(url, STORE_SESSION), index=index_config(embed)) as store):
        saver.setup()
        store.setup()
        yield saver, store
