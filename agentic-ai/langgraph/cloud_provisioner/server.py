"""AG-UI server: the SAME graph as cli.py, served over HTTP for the web clients.

    web/        browser --> Next.js /api/copilotkit (CopilotRuntime) --> POST :8001/agent --> graph.py
    web_plain/  browser ------------------- fetch + SSE ---------------> POST :8001/agent --> graph.py
    web_hybrid/, web_shadcn/, web_assistant_ui/  browser --> same-origin proxy (Vite / nginx) --> POST :8001/agent --> graph.py
                (web_shadcn and web_assistant_ui also send an A2UI catalog in context, which turns on the A2UI tools; see a2ui.py)

What the web UI gets from AG-UI that cli.py printed by hand:
  STATE_SNAPSHOT        phase / plan / cost / issues / actions  -> the plan panel (useAgent)
  RUN_FINISHED outcome  {type: "interrupt"} from approve's interrupt() -> the approve card (useInterrupt)
  resume[]              the card's resolve({approved}) -> Command(resume=...) -> approve continues
  TOOL_CALL_*           list_catalog, propose_plan, ... -> tool cards in the chat

Who is asking (tenant_id, user_id) is the run's context for long-term memory (memory.py). It
comes from the server's config, never from the request; fixed dev values until there is auth.

    docker compose up -d  # Postgres: checkpoints + long-term memory (persistence.py)
    uv run server.py      # http://localhost:8001/agent
"""

import asyncio
import os
from contextlib import asynccontextmanager

import uvicorn
from ag_ui.core import EventType, RunErrorEvent
from ag_ui.core.types import Context, RunAgentInput
from ag_ui.encoder import EventEncoder
from ag_ui_a2ui_toolkit import A2UI_SCHEMA_CONTEXT_DESCRIPTION
from ag_ui_langgraph import LangGraphAgent
from ag_ui_langgraph.utils import camel_to_snake
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import a2ui
import persistence
from graph import PublicState, State, build_graph, inventory, provider

graph = None  # compiled in lifespan, once Postgres is open
# until there is auth: one dev tenant and user. Real values come from the authenticated session.
IDENTITY = {"tenant_id": os.getenv("DEV_TENANT", "dev-tenant"), "user_id": os.getenv("DEV_USER", "dev-user"),
            "agent_id": "provisioner"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    global graph
    # Same database as cli.py. The checkpointer is what lets a run PAUSE at approve and resume
    # in a later HTTP request (or after a server restart); the store is long-term memory.
    async with persistence.open_async() as (saver, store):
        graph = build_graph().compile(checkpointer=saver, store=store)
        yield


app = FastAPI(lifespan=lifespan)

# web_plain/ (:5173) calls this server straight from the browser (no runtime or proxy in
# between), from another origin, so the browser needs CORS permission.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# forwardedProps the adapter treats as orders: nodeName writes the request's `state` into the
# checkpoint AS that node and continues from there (nodeName="approve" -> straight to apply),
# command.resume is the legacy resume. The browser may not steer the graph.
UNTRUSTED_PROPS = {"nodeName", "node_name", "command"}
# The adapter also merges forwardedProps (snake_cased) into the graph INPUT, so a prop named like
# a state key would write it: "outcome" would forge a memory record, "memoryContext" the recalled
# cases, "plan" a plan. None of them may come from the browser.
STATE_KEYS = set(State.__annotations__)


async def trusted(input_data: RunAgentInput) -> RunAgentInput:
    """The browser's `state` is a copy for display only. Replace it with the thread's own
    checkpoint, so a client can't hand the graph a plan that never passed policy and approval."""
    saved = await graph.aget_state({"configurable": {"thread_id": input_data.thread_id}})
    # ag-ui-langgraph resumes whatever is paused, whatever interruptId the client sends. Each pause
    # has its own id, so an answer to an old card (stale tab, replay) must not land on a newer plan.
    open_ids = {i.id for i in saved.interrupts}
    stale = [r.interrupt_id for r in input_data.resume or [] if r.interrupt_id not in open_ids]
    if stale:
        raise HTTPException(409, f"not an open interrupt on this thread: {stale}; reload the thread")
    public = set(PublicState.__annotations__) - {"messages"}
    state = {k: v for k, v in (saved.values or {}).items() if k in public}
    props = {k: v for k, v in (input_data.forwarded_props or {}).items()
             if k not in UNTRUSTED_PROPS and camel_to_snake(k) not in STATE_KEYS}
    return input_data.model_copy(update={"state": state, "forwarded_props": props,
                                         "context": trusted_context(input_data.context)})


def trusted_context(context: list[Context]) -> list[Context]:
    """RunAgentInput.context is text the adapter hands to the A2UI sub-agent's prompt. Keep only
    the A2UI catalog entry, and only as the server's own catalog (a2ui.VIEW_CATALOG): the browser
    says WHICH catalog it renders, the server says what an LLM may put in it."""
    kept = []
    for c in context or []:
        if c.description == A2UI_SCHEMA_CONTEXT_DESCRIPTION and (ours := a2ui.server_catalog(c.value)):
            kept.append(c.model_copy(update={"value": ours}))
    return kept


class ThreadLocks:
    """One graph run at a time per thread. Without it, two answers to one pause (a double-click,
    two tabs) both pass the open-interrupt check, then both resume the same checkpoint; a new
    message racing an answer does the same. Process-local: with several server processes this
    needs a shared lock (e.g. a Postgres advisory lock or a Redis lease keyed by thread id)."""

    def __init__(self):
        self._locks: dict[str, asyncio.Lock] = {}
        self._users: dict[str, int] = {}

    @asynccontextmanager
    async def hold(self, thread_id: str):
        lock = self._locks.setdefault(thread_id, asyncio.Lock())
        self._users[thread_id] = self._users.get(thread_id, 0) + 1
        try:
            async with lock:  # released on finish, graph error, and client disconnect (cancellation)
                yield
        finally:
            self._users[thread_id] -= 1
            if not self._users[thread_id]:  # nobody holds or waits: forget the thread
                del self._users[thread_id], self._locks[thread_id]


thread_locks = ThreadLocks()


@app.post("/agent")
async def agent_endpoint(input_data: RunAgentInput, request: Request):
    # In a real deployment: authenticate here, and decide who may approve
    # (e.g. only an ops role may approve prod) before the graph ever runs.
    input_data = await trusted(input_data)  # a plainly stale answer gets HTTP 409 right away
    agent = LangGraphAgent(
        name="default",
        description="Cloud provisioning assistant",
        graph=graph,
        # the apply loop is one step per resource; configurable becomes the run's context
        config={"recursion_limit": 100, "configurable": IDENTITY},
        emit_interrupt_outcome=True,         # standard AG-UI interrupts: RUN_FINISHED outcome + resume[]
        enable_legacy_on_interrupt_event=False,
        emit_raw_events=False,
    )
    encoder = EventEncoder(accept=request.headers.get("accept"))

    async def events():
        # The graph runs while this generator is consumed, so the lock is taken here and held
        # for the whole run, not just around the check.
        async with thread_locks.hold(input_data.thread_id):
            try:
                # Again, under the lock: the pause may have been answered while this request waited.
                # The response has already started (200), so the refusal is an AG-UI RUN_ERROR.
                checked = await trusted(input_data)
            except HTTPException as e:
                yield encoder.encode(RunErrorEvent(type=EventType.RUN_ERROR, message=e.detail, code="interrupt_closed"))
                return
            async for event in agent.run(checked):
                yield encoder.encode(event)

    return StreamingResponse(events(), media_type=encoder.get_content_type())


@app.get("/inventory")
def list_inventory():
    """What exists now, for the UI's inventory panel (read-only)."""
    return {"provider": provider.name,
            "resources": [{"name": n, **{k: r[k] for k in ("kind", "env", "region", "cloud_id")}}
                          for n, r in inventory.all().items()]}


@app.get("/agent/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)
