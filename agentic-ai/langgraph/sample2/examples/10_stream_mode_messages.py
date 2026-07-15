"""stream_mode="messages" — stream LLM tokens as they're generated inside a node.

Unlike "values"/"updates" (which stream per super-step), "messages" streams
per-token from any chat model called inside a node, even if that node calls
.invoke() rather than .stream() on the model — LangGraph taps into the model's
own streaming under the hood.

Uses GenericFakeChatModel so this runs with no API key required.
"""

from typing import TypedDict

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph


class GraphState(TypedDict):
    name: str
    greeting: str


# a fake chat model that "generates" this fixed reply, one token at a time
fake_model = GenericFakeChatModel(
    messages=iter([AIMessage(content="Hello there, nice to meet you!")])
)


def greet(state: GraphState) -> GraphState:
    response = fake_model.invoke(f"Greet {state['name']}")
    return {"greeting": response.content}


graph = StateGraph(GraphState)
graph.add_node("greet", greet)
graph.add_edge(START, "greet")
graph.add_edge("greet", END)
app = graph.compile()


if __name__ == "__main__":
    print("streaming tokens as they arrive:")
    full_text = ""
    for message_chunk, metadata in app.stream({"name": "sample2"}, stream_mode="messages"):
        full_text += message_chunk.content
        print(f"  node={metadata['langgraph_node']!r} chunk={message_chunk.content!r}")

    print(f"\nassembled: {full_text!r}")
