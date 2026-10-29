"""Tests run against the provisioner_test database (docker compose up -d), with a fake embedding,
a scripted chat model, the fake cloud without delays, and a throwaway inventory."""

import hashlib
import math
import os
import re
import sys
import uuid
from pathlib import Path

os.environ.update(CLOUD_PROVIDER="fake", FAKE_DELAY="0", EMBED_DIMS="64")
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

import graph
import persistence
from cloud import FakeCloud, Inventory
from memory import RequestContext

TEST_DB = os.getenv("TEST_DATABASE_URL", "postgresql://provisioner:provisioner@127.0.0.1:5434/provisioner_test")


def fake_embed(texts: list[str]) -> list[list[float]]:
    """Bag of words hashed into 64 dims: texts that share words are close. Deterministic, offline."""
    out = []
    for text in texts:
        v = [0.0] * 64
        for w in re.findall(r"[a-z0-9.]+", text.lower()):
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 64] += 1
        n = math.sqrt(sum(x * x for x in v)) or 1
        out.append([x / n for x in v])
    return out


@pytest.fixture(scope="session")
def pg():
    try:
        psycopg.connect(TEST_DB, connect_timeout=2).close()
    except psycopg.OperationalError as e:
        pytest.skip(f"no test database ({e}); run `docker compose up -d`")
    with persistence.open_sync(TEST_DB, embed=fake_embed) as (saver, store):
        yield saver, store


@pytest.fixture
def store(pg):
    return pg[1]


@pytest.fixture
def saver(pg):
    return pg[0]


@pytest.fixture
def ctx():
    """A fresh tenant per test: tests never see each other's records."""
    return RequestContext(tenant_id=f"t-{uuid.uuid4().hex[:8]}", user_id="u1", thread_id=uuid.uuid4().hex[:8])


@pytest.fixture(autouse=True)
def cloud(tmp_path, monkeypatch):
    """Never the real inventory.db; a fresh fake cloud (its fail-once memory) per test."""
    monkeypatch.setattr(graph, "inventory", Inventory(tmp_path / "inventory.db"))
    monkeypatch.setattr(graph, "provider", FakeCloud())


class ScriptedModel(BaseChatModel):
    """Answers with the next scripted AIMessage, and keeps every prompt it was given."""
    replies: list
    prompts: list = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.prompts.append(messages)
        return ChatResult(generations=[ChatGeneration(message=self.replies.pop(0))])


@pytest.fixture
def scripted(monkeypatch):
    """scripted(*replies) -> the model; build_graph() then uses it instead of a real LLM."""
    def make(*replies):
        model = ScriptedModel(replies=list(replies), prompts=[])
        monkeypatch.setattr(graph, "init_chat_model", lambda *a, **k: model)
        return model
    return make


def call(name: str, args: dict, id: str | None = None) -> AIMessage:
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": id or f"call-{uuid.uuid4().hex[:6]}"}])
