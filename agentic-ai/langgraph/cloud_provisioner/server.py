"""AG-UI server: the SAME graph as cli.py, served over HTTP for the web clients.

    web/        browser --> Next.js /api/copilotkit (CopilotRuntime) --> POST :8001/agent --> graph.py
    web_plain/  browser ------------------- fetch + SSE ---------------> POST :8001/agent --> graph.py
    web_hybrid/, web_shadcn/  browser --> same-origin proxy (Vite / nginx) --> POST :8001/agent --> graph.py
                (web_shadcn also sends an A2UI catalog in context, which turns on the A2UI tools; see a2ui.py)

What the web UI gets from AG-UI that cli.py printed by hand:
  STATE_SNAPSHOT        phase / plan / cost / issues / actions  -> the plan panel (useAgent)
  RUN_FINISHED outcome  {type: "interrupt"} from approve's interrupt() -> the approve card (useInterrupt)
  resume[]              the card's resolve({approved}) -> Command(resume=...) -> approve continues
  TOOL_CALL_*           list_catalog, propose_plan, ... -> tool cards in the chat

    uv run server.py      # http://localhost:8001/agent
"""

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from ag_ui.core.types import RunAgentInput
from ag_ui.encoder import EventEncoder
from ag_ui_langgraph import LangGraphAgent
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from graph import build_graph, inventory, provider

HERE = Path(__file__).parent
graph = None  # compiled in lifespan, once the checkpoint db is open


@asynccontextmanager
async def lifespan(_: FastAPI):
    global graph
    # Same file as cli.py. The checkpointer is what lets a run PAUSE at approve
    # and resume in a later HTTP request (or after a server restart).
    async with AsyncSqliteSaver.from_conn_string(str(HERE / "checkpoints.db")) as saver:
        graph = build_graph().compile(checkpointer=saver)
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


@app.post("/agent")
async def agent_endpoint(input_data: RunAgentInput, request: Request):
    # In a real deployment: authenticate here, and decide who may approve
    # (e.g. only an ops role may approve prod) before the graph ever runs.
    agent = LangGraphAgent(
        name="default",
        description="Cloud provisioning assistant",
        graph=graph,
        config={"recursion_limit": 100},     # the apply loop is one step per resource
        emit_interrupt_outcome=True,         # standard AG-UI interrupts: RUN_FINISHED outcome + resume[]
        enable_legacy_on_interrupt_event=False,
        emit_raw_events=False,
    )
    encoder = EventEncoder(accept=request.headers.get("accept"))

    async def events():
        async for event in agent.run(input_data):
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
