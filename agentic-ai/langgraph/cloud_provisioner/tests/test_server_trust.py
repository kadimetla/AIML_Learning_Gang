"""server.trusted(): the browser cannot write memory (or any state) through forwardedProps."""

import asyncio
from types import SimpleNamespace

from ag_ui.core.types import RunAgentInput

import server


class SavedThread:
    async def aget_state(self, config):
        return SimpleNamespace(interrupts=[], values={
            "messages": [], "phase": "idle", "plan": None, "memory_context": [{"x": 1}], "outcome": None})


def test_forwarded_props_cannot_set_state_keys(monkeypatch):
    monkeypatch.setattr(server, "graph", SavedThread())
    forged = {"outcome": {"kind": "done"}, "memoryContext": [{"outcome": "done"}], "plan": {"env": "prod"},
              "callId": "x", "messages": ["hi"], "nodeName": "apply", "streamSubgraphs": False}
    request = RunAgentInput(thread_id="t1", run_id="r1", state={}, messages=[], tools=[], context=[],
                            forwarded_props=forged)
    checked = asyncio.run(server.trusted(request))
    assert checked.forwarded_props == {"streamSubgraphs": False}
    assert set(checked.state) == {"phase", "plan"}  # public keys only, from the checkpoint


def test_identity_comes_from_the_server_config():
    assert {"tenant_id", "user_id", "agent_id"} <= set(server.IDENTITY)
