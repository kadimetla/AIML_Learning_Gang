"""AG-UI server: the SAME graph as chat.py, served over HTTP for the CopilotKit web UI.

    browser (CopilotChat) --> Next.js /api/copilotkit (CopilotRuntime)
                          --> POST http://localhost:8000/agent   (AG-UI over SSE)
                          --> this file --> build_graph() from chat.py

What changes vs chat.py is only the OUTER loop:
  chat.py    input() -> app.stream()   -> print()
  server.py  AG-UI RunAgentInput -> ag_ui_langgraph -> app.astream_events() -> AG-UI events

  thread_id  comes from AG-UI `threadId` (CopilotChat's threadId prop)
  user_id    comes from AG-UI `forwardedProps.user_id` (CopilotKitProvider's
             `properties`). DEMO ONLY: a real app must take the user from its
             own auth (session/JWT) here, never from what the browser sends.

    uv run server.py      # http://localhost:8000/agent
"""

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from ag_ui.core.types import RunAgentInput
from ag_ui.encoder import EventEncoder
from ag_ui_langgraph import LangGraphAgent
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.sqlite import SqliteStore

from chat import STORE_INDEX, build_graph

HERE = Path(__file__).parent
graph = None  # compiled in lifespan, once the databases are open


@asynccontextmanager
async def lifespan(_: FastAPI):
    global graph
    # Same two files as chat.py, so the terminal and the web UI share memories.
    # The AG-UI adapter runs the graph with astream_events, so the checkpointer
    # must be the async variant.
    async with AsyncSqliteSaver.from_conn_string(str(HERE / "checkpoints.db")) as saver:
        with SqliteStore.from_conn_string(str(HERE / "memories.db"), index=STORE_INDEX) as store:
            store.setup()
            graph = build_graph().compile(checkpointer=saver, store=store)
            yield


app = FastAPI(lifespan=lifespan)


@app.post("/agent")
async def agent_endpoint(input_data: RunAgentInput, request: Request):
    # Identity enters here: user_id goes into the graph config, next to the
    # thread_id the adapter adds from input_data.thread_id.
    user_id = (input_data.forwarded_props or {}).get("user_id") or "anonymous"
    agent = LangGraphAgent(
        name="default",
        description="Chat assistant with memory, tools and skills",
        graph=graph,
        config={"configurable": {"user_id": user_id}},
        emit_raw_events=False,  # only standard AG-UI events on the wire
    )
    encoder = EventEncoder(accept=request.headers.get("accept"))

    async def events():
        async for event in agent.run(input_data):
            yield encoder.encode(event)

    return StreamingResponse(events(), media_type=encoder.get_content_type())


@app.get("/agent/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
