"""Tiny script that only works once requirements.txt is installed.

    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python demo.py
"""

import requests
from rich import print

resp = requests.get("https://pypi.org/pypi/pip/json", timeout=5)
latest = resp.json()["info"]["version"]
print(f"[bold green]Latest pip release on PyPI:[/bold green] {latest}")
