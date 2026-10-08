"""POST /chat {question, history} -> {answer, sources, steps}"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from ragstore import settings

from .graph import build_graph, sources_of
from ragstore.config import ROOT

app = FastAPI(title="RAG query")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_graph = None


class ChatIn(BaseModel):
    question: str
    history: list[dict] = []


@app.post("/chat")
def chat(body: ChatIn):
    global _graph
    _graph = _graph or build_graph()
    out = _graph.invoke({"question": body.question, "history": body.history, "steps": []})
    return {"answer": out["answer"], "sources": sources_of(out.get("relevant") or []), "steps": out["steps"]}


@app.get("/config")
def config():
    return {"backend": settings.backend, "collection": settings.collection, "chat_model": settings.chat_model}


@app.get("/")
def ui():
    return FileResponse(ROOT / "ui" / "index.html")


def serve() -> None:
    uvicorn.run(app, host="127.0.0.1", port=settings.query_port)


if __name__ == "__main__":
    serve()
