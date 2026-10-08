"""Compare chunking strategies on retrieval quality (no LLM calls, only embeddings).

A retrieved chunk counts as a HIT when it contains one of the question's `answer` strings, so a
chunking that splits the answer across two chunks (or buries it in a huge chunk) scores worse.

    uv run python eval/compare_chunking.py
    uv run python eval/compare_chunking.py --docs my.md --questions my_questions.json --k 5

Metrics (higher is better):  hit@1 / hit@3 / hit@k = share of questions with a relevant chunk in the
top 1/3/k;  MRR = mean 1/rank of the first relevant chunk.  Chunks and avg-len describe the index size.
Runs against a throwaway chroma collection per config and deletes them afterwards.
"""

import argparse
import json
import statistics
from pathlib import Path

from ragstore import get_vectorstore
from ragstore.store import _chroma_client

from ragingestion.chunking import chunk
from ragingestion.loaders import load_file

HERE = Path(__file__).parent
# (strategy, size, overlap). Sizes are characters, except "token" which is tokens.
CONFIGS = [
    ("fixed", 800, 100),
    ("recursive", 200, 30),
    ("recursive", 400, 60),
    ("recursive", 800, 100),
    ("recursive", 1500, 200),
    ("markdown", 800, 100),
    ("token", 100, 15),
    ("token", 250, 40),
]


def evaluate(docs, questions, strategy, size, overlap, k):
    name = f"eval_{strategy}_{size}_{overlap}"
    chunks = chunk(docs, strategy, size, overlap)
    vs = get_vectorstore(name, backend="chroma")
    vs.add_documents(chunks)
    hits = {1: 0, 3: 0, k: 0}
    rr = []
    for item in questions:
        needles = [a.lower() for a in item["answer"]]
        results = vs.similarity_search(item["q"], k=k)
        rank = next((i for i, d in enumerate(results, 1)
                     if any(n in " ".join(d.page_content.lower().split()) for n in needles)), None)
        rr.append(1 / rank if rank else 0.0)
        for cut in hits:
            hits[cut] += bool(rank and rank <= cut)
    n = len(questions)
    return {"config": f"{strategy:9} {size:>4}/{overlap:<3}", "chunks": len(chunks),
            "avg_len": round(statistics.mean(len(c.page_content) for c in chunks)),
            **{f"hit@{c}": hits[c] / n for c in sorted(hits)}, "mrr": statistics.mean(rr), "name": name}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--docs", type=Path, default=HERE / "corpus.md")
    p.add_argument("--questions", type=Path, default=HERE / "questions.json")
    p.add_argument("--k", type=int, default=5)
    a = p.parse_args()

    docs = load_file(a.docs)
    questions = json.loads(a.questions.read_text())
    print(f"{a.docs.name}: {sum(len(d.page_content) for d in docs)} chars, {len(questions)} questions, k={a.k}\n")

    rows = []
    try:
        for cfg in CONFIGS:
            rows.append(evaluate(docs, questions, *cfg, a.k))
    finally:
        client = _chroma_client()
        for c in client.list_collections():
            if (c if isinstance(c, str) else c.name).startswith("eval_"):
                client.delete_collection(c if isinstance(c, str) else c.name)

    keys = ["chunks", "avg_len", "hit@1", "hit@3", f"hit@{a.k}", "mrr"]
    print(f"{'config':18}" + "".join(f"{k:>9}" for k in keys))
    for r in sorted(rows, key=lambda r: (-r["mrr"], -r[f"hit@{a.k}"])):
        print(f"{r['config']:18}" + "".join(f"{r[k]:>9.2f}" if isinstance(r[k], float) else f"{r[k]:>9}" for k in keys))
    print("\nSorted by MRR. Tip: re-run with your own --docs/--questions; best chunking is corpus-specific.")


if __name__ == "__main__":
    main()
