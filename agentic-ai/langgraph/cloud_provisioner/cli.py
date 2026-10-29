"""Terminal chat for the provisioning graph. The approval step is a y/N prompt.

    docker compose up -d           # Postgres: checkpoints + long-term memory
    uv run cli.py                  # new thread on the fake cloud
    uv run cli.py --thread abc     # resume a thread (even one paused at approval)
    uv run cli.py --tenant acme --user sam   # whose long-term memory (default: the dev tenant/user)
    REPL commands: /inventory  /new  /quit
"""

import argparse
import uuid

from langgraph.types import Command

import persistence
from graph import build_graph, inventory
ICON = {"ready": "✓", "deleted": "✓", "retrying": "↻", "failed": "✗", "pending": "·"}


def show_plan(state: dict):
    p, cost = state["plan"], state["cost"]
    print(f"\n  {'DESTROY' if p['destroy'] else 'PLAN'} {p['env']} / {p['region']}")
    for a in state["actions"]:
        print(f"    {a['op']:6} {a['kind']:15} {a['name']:28} ${cost['lines'].get(a['name'], 0):>7.2f}")
    print(f"    {'':51}total ${cost['total']:>7.2f}/month")


def turn(app, payload, config, approver, context: dict | None = None) -> str:
    """Run until the graph ends. At each approval pause, ask approver(state) and resume.
    context (tenant_id, user_id, thread_id) is not checkpointed: it goes with every run, resumes too."""
    reply = ""
    while True:
        paused = None
        for update in app.stream(payload, config, stream_mode="updates", context=context):
            for node, delta in update.items():
                if node == "__interrupt__":
                    paused = delta[0].value
                    continue
                delta = delta or {}
                for msg in delta.get("messages", []):
                    if node == "agent" and msg.tool_calls:
                        for c in msg.tool_calls:
                            print(f"  [agent → {c['name']}] {str(c['args'])[:110]}")
                    elif node == "agent":
                        reply = msg.content
                    else:
                        print(f"  [{node} → result] {msg.content[:300]}")
                if node == "apply":
                    a = next(a for a in reversed(delta["actions"]) if a["attempts"])
                    print(f"  [apply] {ICON[a['status']]} {a['op']} {a['name']} {a['status']}"
                          + (f" ({a['error'][:60]})" if a["error"] else ""))
                elif node == "estimate":
                    print(f"  [estimate] ${delta['cost']['total']}/month")
                elif node == "plan" and delta.get("actions"):
                    print(f"  [plan] {len(delta['actions'])} actions")
        if paused is None:
            return reply
        print(f"\n  ⏸  {paused['message']}")
        show_plan(app.get_state(config).values)
        payload = Command(resume=approver(paused))


def ask_human(_: dict) -> dict:
    yes = input("  approve? [y/N] ").strip().lower() == "y"
    return {"approved": True} if yes else {"approved": False, "reason": input("  why not? ").strip()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--thread", default=None)
    parser.add_argument("--tenant", default="dev-tenant")
    parser.add_argument("--user", default="dev-user")
    args = parser.parse_args()
    with persistence.open_sync() as (saver, store):
        app = build_graph().compile(checkpointer=saver, store=store)
        thread = args.thread or uuid.uuid4().hex[:8]
        print(f"thread={thread}   (/inventory /new /quit)")
        while True:
            try:
                text = input("\nyou> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text in ("/quit", "/exit"):
                break
            if text == "/new":
                thread = uuid.uuid4().hex[:8]
                print(f"new thread={thread}")
                continue
            if text == "/inventory":
                for n, r in inventory.all().items():
                    print(f"  {r['env']:8} {r['kind']:15} {n:28} {r['cloud_id']}")
                continue
            if text:
                config = {"configurable": {"thread_id": thread}, "recursion_limit": 100}
                context = {"tenant_id": args.tenant, "user_id": args.user, "thread_id": thread}
                print(f"\nbot> {turn(app, {'messages': [('user', text)]}, config, ask_human, context)}")


if __name__ == "__main__":
    main()
