"""Compare document loaders on extraction quality and retrieval quality (embeddings only, no LLM).

For every loader that supports a sample file we report:
  time    - seconds to load all of its files
  recall  - share of questions whose answer string appears anywhere in the extracted text
            (did the loader get the information out at all?)
  hit@1/k - share of questions whose answer appears in the top-1 / top-k retrieved chunk
            (does it survive chunking + search, with all files in one throwaway collection?)

    uv run python eval/compare_loaders.py
    uv run python eval/compare_loaders.py --loaders pypdf ocr docling --k 3

Answers match case/whitespace-insensitively; list several alternatives when a layout may differ.
Loaders whose optional dependency is missing or fail on a file are reported, not fatal.
"""

import argparse
import json
import logging
import time
from pathlib import Path

from ragstore import get_vectorstore
from ragstore.store import _chroma_client

from ragingestion.chunking import chunk
from ragingestion.loaders import _LOADERS, load_file

HERE = Path(__file__).parent
SAMPLES = HERE.parent.parent / "data" / "samples"
norm = lambda s: " ".join(s.lower().split())  # noqa: E731


def run(loader: str, files: list[str], questions: list[dict], k: int) -> dict:
    exts = _LOADERS[loader][1]
    files = [f for f in files if Path(f).suffix.lower() in exts]
    qs = [q for q in questions if q["file"] in files]
    if not qs:
        return {"loader": loader, "note": "no sample files for this loader"}
    t0, docs, errors = time.perf_counter(), [], []
    for f in files:
        try:
            docs += load_file(SAMPLES / f, f, loader=loader)
        except Exception as e:  # missing optional dep, bad file, ...
            errors.append(f"{f}: {type(e).__name__}: {str(e)[:60]}")
    elapsed = time.perf_counter() - t0
    text = norm(" ".join(d.page_content for d in docs))
    recall = sum(any(norm(a) in text for a in q["answer"]) for q in qs) / len(qs)
    out = {"loader": loader, "files": len(files), "questions": len(qs), "time": elapsed,
           "chars": len(text), "recall": recall, "errors": errors}
    if docs:
        vs = get_vectorstore(f"eval_loader_{loader}", backend="chroma")
        vs.add_documents(chunk(docs, "recursive", 800, 100))
        h1 = hk = 0
        for q in qs:
            res = [norm(d.page_content) for d in vs.similarity_search(q["q"], k=k)]
            ok = [any(norm(a) in r for a in q["answer"]) for r in res]
            h1 += bool(ok and ok[0])
            hk += any(ok)
        out |= {"hit@1": h1 / len(qs), f"hit@{k}": hk / len(qs)}
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--loaders", nargs="+", default=["pypdf", "pymupdf4llm", "ocr", "docling"])
    p.add_argument("--questions", type=Path, default=HERE / "loader_questions.json")
    p.add_argument("--k", type=int, default=3)
    a = p.parse_args()
    logging.disable(logging.WARNING)
    questions = json.loads(a.questions.read_text())
    files = sorted({q["file"] for q in questions})
    print(f"{len(files)} files, {len(questions)} questions, k={a.k}\n")

    rows = []
    try:
        for name in a.loaders:
            rows.append(run(name, files, questions, a.k))
    finally:
        client = _chroma_client()
        for c in client.list_collections():
            if (c if isinstance(c, str) else c.name).startswith("eval_loader_"):
                client.delete_collection(c if isinstance(c, str) else c.name)

    cols = ["questions", "time", "chars", "recall", "hit@1", f"hit@{a.k}"]
    print(f"{'loader':13}" + "".join(f"{c:>10}" for c in cols))
    for r in rows:
        if "note" in r:
            print(f"{r['loader']:13}{r['note']}")
            continue
        print(f"{r['loader']:13}" + "".join(
            f"{r[c]:>10.2f}" if isinstance(r.get(c), float) else f"{r.get(c, '-'):>10}" for c in cols))
        for e in r["errors"]:
            print(f"{'':13}! {e}")
    print("\nrecall = answer found in extracted text; hit@N = answer in top-N retrieved chunks.")


if __name__ == "__main__":
    main()
