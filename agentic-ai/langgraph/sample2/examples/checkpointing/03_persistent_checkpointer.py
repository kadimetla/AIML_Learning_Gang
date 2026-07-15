"""InMemorySaver (used everywhere else in this project) is lost the moment
the process exits -- fine for demos, useless for anything that needs to
survive a restart. SqliteSaver persists checkpoints to an actual file on
disk, so a completely separate process can pick up the same thread_id later.

This file simulates "two separate processes" by using two separate `with`
blocks (each opens and closes its own connection), sharing only the sqlite
file path between them -- nothing is kept in Python memory across the two.
"""

import pathlib
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph


class GraphState(TypedDict):
    counter: int


def increment(state: GraphState) -> GraphState:
    return {"counter": state["counter"] + 1}


def build_graph() -> StateGraph:
    graph = StateGraph(GraphState)
    graph.add_node("increment", increment)
    graph.add_edge(START, "increment")
    graph.add_edge("increment", END)
    return graph


DB_PATH = pathlib.Path(__file__).parent / "checkpoints.db"


if __name__ == "__main__":
    DB_PATH.unlink(missing_ok=True)  # start clean each run of this demo
    config = {"configurable": {"thread_id": "persistent-thread-1"}}

    # "process 1": run the graph once, then close the connection entirely
    with SqliteSaver.from_conn_string(str(DB_PATH)) as saver:
        app = build_graph().compile(checkpointer=saver)
        result = app.invoke({"counter": 0}, config=config)
        print(f"process 1 result: {result}")

    print(f"{DB_PATH.name} now on disk, {DB_PATH.stat().st_size} bytes")

    # "process 2": brand new SqliteSaver connection, same file -- nothing
    # from the Python objects above is reused, only the file on disk
    with SqliteSaver.from_conn_string(str(DB_PATH)) as saver:
        app = build_graph().compile(checkpointer=saver)
        state = app.get_state(config)
        print(f"process 2 recovered state from disk: {state.values}")
        print(f"process 2 recovered next-to-run: {state.next!r}")  # () -- thread already finished

    DB_PATH.unlink(missing_ok=True)  # clean up after the demo
