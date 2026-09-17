"""Pattern 3: query routing -- a router node classifies the incoming
question and sends it down one of two branches before any retrieval
happens:

    route(question) --repo_docs--> retrieve -> generate -> END
                |
                '--general------> answer_directly -> END

Contrast with the other two patterns: 01 lets the LLM decide per-turn
whether to call a retrieval tool (mid-conversation); 02 always retrieves
and self-corrects the query. Here the branch decision is made once, up
front, before retrieval is even attempted -- useful when retrieval is
expensive/slow and you want to skip it entirely for questions it can't
help with.

Run: uv run query_flows/03_query_routing.py
"""

from typing import Literal, TypedDict

from dotenv import load_dotenv

load_dotenv()

from langchain.chat_models import init_chat_model
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from store import format_docs, load_faiss_retriever

retriever = load_faiss_retriever(k=4)
llm = init_chat_model("litellm:gpt-4o-mini", temperature=0)


class GraphState(TypedDict):
    question: str
    datasource: str
    answer: str


class RouteQuery(BaseModel):
    datasource: Literal["repo_docs", "general"] = Field(
        description=(
            "'repo_docs' if the question is about this specific workspace/repo's "
            "code, samples, or docs; 'general' for anything else answerable from "
            "general knowledge."
        )
    )


def route_node(state: GraphState) -> dict:
    router = llm.with_structured_output(RouteQuery)
    decision = router.invoke(state["question"])
    print(f"  [route] -> {decision.datasource}")
    return {"datasource": decision.datasource}


def route_condition(state: GraphState) -> Literal["retrieve_and_generate", "answer_directly"]:
    return "retrieve_and_generate" if state["datasource"] == "repo_docs" else "answer_directly"


def retrieve_and_generate_node(state: GraphState) -> dict:
    docs = retriever.invoke(state["question"])
    context = format_docs(docs) if docs else "(no documents found)"
    response = llm.invoke(
        f"Answer the question using only the context below.\n\nContext:\n{context}\n\n"
        f"Question: {state['question']}"
    )
    return {"answer": response.content}


def answer_directly_node(state: GraphState) -> dict:
    response = llm.invoke(state["question"])
    return {"answer": response.content}


graph = StateGraph(GraphState)
graph.add_node("route", route_node)
graph.add_node("retrieve_and_generate", retrieve_and_generate_node)
graph.add_node("answer_directly", answer_directly_node)

graph.add_edge(START, "route")
graph.add_conditional_edges(
    "route",
    route_condition,
    {"retrieve_and_generate": "retrieve_and_generate", "answer_directly": "answer_directly"},
)
graph.add_edge("retrieve_and_generate", END)
graph.add_edge("answer_directly", END)

app = graph.compile()


def main():
    for question in [
        "What tools does sample3's ToolNode dispatch in this repo?",
        "What's the capital of France?",
    ]:
        print(f"\n=== {question} ===")
        result = app.invoke({"question": question, "datasource": "", "answer": ""})
        print(f"[answer]\n{result['answer']}")


if __name__ == "__main__":
    main()
