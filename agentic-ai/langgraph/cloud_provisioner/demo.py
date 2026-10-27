"""Scripted run on the fake cloud: policy fix, a rejection, approve + apply with a retry, then destroy.

    uv run demo.py
"""

import uuid

from langgraph.checkpoint.memory import InMemorySaver

from cli import turn
from graph import build_graph, inventory, provider

answers = iter([
    {"approved": False, "reason": "use t3.micro for the web servers, it is only staging"},
    {"approved": True},
    {"approved": True},
])


def scripted(paused: dict) -> dict:
    decision = next(answers)
    print(f"  approve? {'y' if decision['approved'] else 'n  -- ' + decision['reason']}")
    return decision


def say(app, text, config):
    print(f"\n{'=' * 90}\nyou> {text}")
    print(f"\nbot> {turn(app, {'messages': [('user', text)]}, config, scripted)}")


def main():
    if provider.name != "fake":
        raise SystemExit("demo.py is for the fake cloud only (it forgets inventory records)")
    for name, rec in inventory.all().items():  # start clean: forget earlier demo-staging runs
        if rec["env"] == "staging":
            inventory.remove(name)
    app = build_graph().compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": uuid.uuid4().hex[:8]}, "recursion_limit": 100}

    say(app, "Create a staging env in us-east-1 for a web app: 2 web servers (t3.small) behind "
             "port 443 open to everyone, SSH open to everyone too, and a small postgres database "
             "I can reach from my laptop. Budget $120/month.", config)
    say(app, "What exists in staging now?", config)
    say(app, "Tear down staging.", config)


if __name__ == "__main__":
    main()
