"""RetryPolicy -- automatically re-run a node that raises, with exponential
backoff, instead of failing the whole graph on the first transient error.

Attach it per-node via graph.add_node(..., retry_policy=RetryPolicy(...)).
Useful for exactly the kind of thing examples/tool_node_weather/ does -- a
tool that calls a real, occasionally-flaky external API.
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy


class GraphState(TypedDict):
    attempts: int


attempt_counter = {"n": 0}


def flaky_api_call(state: GraphState) -> GraphState:
    attempt_counter["n"] += 1
    if attempt_counter["n"] < 3:
        # simulate a transient failure, e.g. a timeout on the first 2 calls
        raise ValueError(f"transient failure on attempt {attempt_counter['n']}")
    return {"attempts": attempt_counter["n"]}


graph = StateGraph(GraphState)
graph.add_node(
    "flaky_api_call",
    flaky_api_call,
    retry_policy=RetryPolicy(
        max_attempts=5,
        initial_interval=0.01,  # kept tiny so this example runs instantly
        jitter=False,
        # LangGraph's default retry_on skips ValueError/TypeError/etc as
        # "likely a bug, not worth retrying" -- only ConnectionError and
        # 5xx HTTP responses are retried by default. Override it explicitly
        # for anything else you *do* want retried, like our simulated error.
        retry_on=(ValueError,),
    ),
)
graph.add_edge(START, "flaky_api_call")
graph.add_edge("flaky_api_call", END)
app = graph.compile()


if __name__ == "__main__":
    result = app.invoke({"attempts": 0})
    print(f"succeeded after retries: {result}")
    print(f"total calls made: {attempt_counter['n']}")
