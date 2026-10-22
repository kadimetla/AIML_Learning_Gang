"""Scripted, non-interactive run of chat.py that shows both memory layers.

  thread A  tell it a fact (-> save_memory), ask a refund question (-> skill + tool),
            then a follow-up that only works with SHORT-term memory ("that order")
  thread B  brand-new thread: history is empty, but LONG-term memory still knows
            the fact from thread A (-> recall + meal-planner skill)

    uv run demo.py           # uses user "demo"; its memories are wiped at start
"""

import uuid

from chat import build_graph, chat_turn, open_stores

USER = "demo"


def main():
    saver_cm, store_cm = open_stores()
    with saver_cm as saver, store_cm as store:
        store.setup()
        for item in store.search(("memories", USER), limit=100):  # fresh start
            store.delete(("memories", USER), item.key)
        app = build_graph().compile(checkpointer=saver, store=store)

        def run(thread: str, text: str):
            print(f"\n=== thread {thread} | {USER}> {text}")
            config = {"configurable": {"thread_id": thread, "user_id": USER}}
            print(f"bot> {chat_turn(app, text, config)}")

        a, b = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
        run(a, "Hi! I'm vegetarian and allergic to peanuts.")
        run(a, "Can I get a refund on order A300?")
        run(a, "What was the total on that order?")    # short-term memory
        run(b, "What should I cook for dinner tonight?")  # long-term memory

        print("\n=== stored memories")
        for item in store.search(("memories", USER), limit=100):
            print(f"  [{item.key[:8]}] {item.value['fact']}")


if __name__ == "__main__":
    main()
