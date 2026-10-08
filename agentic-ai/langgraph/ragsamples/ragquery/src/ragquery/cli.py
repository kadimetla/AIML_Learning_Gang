"""Usage: uv run ragask "what does the contract say about termination?" """

import sys

from .graph import build_graph, sources_of

q = " ".join(sys.argv[1:])


def main() -> None:
    out = build_graph().invoke({"question": q, "history": [], "steps": []})
    print("\n".join(f"  · {s}" for s in out["steps"]), "\n")
    print(out["answer"])
    for i, s in enumerate(sources_of(out.get("relevant") or []), 1):
        print(f"[{i}] {s['source']} p.{s['page']} chunk {s['chunk']}")


if __name__ == "__main__":
    main()
