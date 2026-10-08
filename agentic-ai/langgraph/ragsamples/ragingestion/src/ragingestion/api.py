"""Upload service used by the UI.  POST /ingest (multipart), GET /documents, DELETE /documents."""

import shutil
import tempfile
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from ragstore import delete_source, list_sources, settings

from .chunking import STRATEGIES
from .pipeline import ingest_file

app = FastAPI(title="RAG ingestion")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/config")
def config():
    return {"backend": settings.backend, "collection": settings.collection, "strategies": STRATEGIES}


@app.post("/ingest")
def ingest(file: UploadFile = File(...), strategy: str = Form("recursive"), size: int = Form(800),
           overlap: int = Form(100)):
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / Path(file.filename).name
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        try:
            return ingest_file(dest, source_name=dest.name, strategy=strategy, size=size, overlap=overlap)
        except ValueError as e:
            raise HTTPException(400, str(e))


@app.get("/documents")
def documents():
    return list_sources()


@app.delete("/documents")
def remove(source: str):
    delete_source(source)
    return {"deleted": source}


def serve() -> None:
    uvicorn.run(app, host="127.0.0.1", port=settings.ingest_port)


if __name__ == "__main__":
    serve()
