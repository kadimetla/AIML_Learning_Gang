"""Pattern 2: corrective RAG -- a fixed graph (not a model-decided tool
call) that grades its own retrieval before answering. Retrieval always
happens first; what's "agentic" is the graph correcting itself:

    retrieve -> grade_docs --relevant-----> generate -> END
                     |
                     '--not relevant--> rewrite_query -> retrieve (loop)

Contrast with 01_retrieval_as_tool.py: there the LLM decides *whether* to
retrieve at all. Here retrieval is unconditional, and the self-correction
is over the *query*, not over whether to search.

Run: uv run query_flows/02_corrective_rag.py
"""

from typing import Literal, TypedDict

from dotenv import load_dotenv

load_dotenv()

from langchain.chat_models import init_chat_model
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from store import format_docs, load_chroma_retriever

MAX_REWRITES = 2

retriever = load_chroma_retriever(k=4)
llm = init_chat_model("litellm:gpt-4o-mini", temperature=0)


class GraphState(TypedDict):
    question: str
    original_question: str
    documents: list
    rewrite_count: int
    relevant: bool
    answer: str


class GradeDocuments(BaseModel):
    """Binary relevance grade for retrieved documents."""

    relevant: bool = Field(description="True if the documents help answer the question.")


class RewrittenQuery(BaseModel):
    query: str = Field(description="A rewritten search query, clearer and more specific.")


def retrieve_node(state: GraphState) -> dict:
    docs = retriever.invoke(state["question"])
    return {"documents": docs}


def grade_documents_node(state: GraphState) -> dict:
    grader = llm.with_structured_output(GradeDocuments)
    context = format_docs(state["documents"]) if state["documents"] else "(no documents)"
    grade = grader.invoke(
        "Do these documents contain information relevant to answering the question?\n\n"
        f"Question: {state['original_question']}\n\nDocuments:\n{context}"
    )
    print(f"  [grade] relevant={grade.relevant} (rewrite_count={state['rewrite_count']})")
    return {"relevant": grade.relevant}


def route_after_grade(state: GraphState) -> Literal["generate", "rewrite_query"]:
    if state["relevant"] or state["rewrite_count"] >= MAX_REWRITES:
        return "generate"
    return "rewrite_query"


def rewrite_query_node(state: GraphState) -> dict:
    rewriter = llm.with_structured_output(RewrittenQuery)
    result = rewriter.invoke(
        "The following search query returned irrelevant documents. Rewrite it to be "
        f"clearer and more specific for a semantic search over README/wiki docs.\n\n"
        f"Original question: {state['original_question']}\nQuery that failed: {state['question']}"
    )
    print(f"  [rewrite] {state['question']!r} -> {result.query!r}")
    return {"question": result.query, "rewrite_count": state["rewrite_count"] + 1}


def generate_node(state: GraphState) -> dict:
    context = format_docs(state["documents"]) if state["documents"] else "(no documents found)"
    response = llm.invoke(
        f"Answer the question using only the context below. If the context doesn't "
        f"contain the answer, say so.\n\nContext:\n{context}\n\n"
        f"Question: {state['original_question']}"
    )
    return {"answer": response.content}


graph = StateGraph(GraphState)
graph.add_node("retrieve", retrieve_node)
graph.add_node("grade_documents", grade_documents_node)
graph.add_node("rewrite_query", rewrite_query_node)
graph.add_node("generate", generate_node)

graph.add_edge(START, "retrieve")
graph.add_edge("retrieve", "grade_documents")
graph.add_conditional_edges(
    "grade_documents",
    route_after_grade,
    {"generate": "generate", "rewrite_query": "rewrite_query"},
)
graph.add_edge("rewrite_query", "retrieve")
graph.add_edge("generate", END)

app = graph.compile()


def main():
    for question in [
        "How does this repo's sample3 wire up parallel tool calls?",
        "How does the corrective RAG sample in sample4 decide when to rewrite the search query?",
    ]:
        print(f"\n=== {question} ===")
        result = app.invoke(
            {
                "question": question,
                "original_question": question,
                "documents": [],
                "rewrite_count": 0,
                "relevant": False,
                "answer": "",
            }
        )
        print(f"\n[answer]\n{result['answer']}")


if __name__ == "__main__":
    main()
