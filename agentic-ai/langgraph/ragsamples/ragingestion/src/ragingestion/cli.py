"""Usage: uv run ragingest docs/*.pdf --strategy recursive --size 800 --overlap 100"""

import argparse
from pathlib import Path

from .chunking import STRATEGIES
from .pipeline import ingest_file


def main() -> None:
    p = argparse.ArgumentParser(description="Ingest files into the vector store")
    p.add_argument("files", nargs="+", type=Path)
    p.add_argument("--strategy", default="recursive", choices=STRATEGIES)
    p.add_argument("--size", type=int, default=800)
    p.add_argument("--overlap", type=int, default=100)
    p.add_argument("--collection")
    a = p.parse_args()
    for f in a.files:
        print(ingest_file(f, collection=a.collection, strategy=a.strategy, size=a.size, overlap=a.overlap))


if __name__ == "__main__":
    main()
