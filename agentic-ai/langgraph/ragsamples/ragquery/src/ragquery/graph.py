"""Agentic RAG as an explicit LangGraph.

        START -> route --(no retrieval)--> answer -> END
                   |
                   v
              retrieve -> grade --(relevant)--> answer -> END
                   ^         |
                   |   (none relevant, retries left)
                   +-- rewrite
                             (none relevant, out of retries) -> answer (says it doesn't know)
"""

from typing import Literal, TypedDict

from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from ragstore import get_vectorstore, settings

MAX_REWRITES = 2


class State(TypedDict, total=False):
    question: str          # original user question
    history: list[dict]    # prior turns [{role, content}]
    query: str             # current (possibly rewritten) search query
    docs: list[Document]   # retrieved candidates
    relevant: list[Document]
    rewrites: int
    answer: str
    steps: list[str]       # human-readable trace shown in the UI


class Route(BaseModel):
    retrieve: bool = Field(description="True if answering needs the user's document knowledge base; "
                                       "False for greetings/small talk/general chit-chat.")


class Grade(BaseModel):
    relevant: bool = Field(description="True if the passage helps answer the question.")


def build_graph(collection: str | None = None, k: int = 5):
    llm = ChatOpenAI(model=settings.chat_model, temperature=0)
    store = get_vectorstore(collection)

    def log(state: State, msg: str) -> list[str]:
        return [*state.get("steps", []), msg]

    def route(state: State):
        r = llm.with_structured_output(Route).invoke(
            "The user has uploaded documents (contents unknown to you). Set retrieve=True for ANY "
            "question that could be answered by them, including questions about rules, policies, "
            "facts or 'my'/'our' things. Set retrieve=False ONLY for pure greetings, thanks or "
            f"chit-chat.\nMessage: {state['question']}")
        return {"query": state["question"], "rewrites": 0,
                "steps": log(state, f"route: {'search documents' if r.retrieve else 'answer directly'}"),
                "docs": [] if r.retrieve else None}

    def after_route(state: State) -> Literal["retrieve", "answer"]:
        return "answer" if state.get("docs") is None else "retrieve"

    def retrieve(state: State):
        docs = store.similarity_search(state["query"], k=k)
        return {"docs": docs, "steps": log(state, f"retrieve: {len(docs)} chunks for “{state['query']}”")}

    def grade(state: State):
        keep = []
        grader = llm.with_structured_output(Grade)
        for d in state["docs"]:
            g = grader.invoke(f"Question: {state['question']}\n\nPassage:\n{d.page_content}\n\n"
                              "Is this passage relevant to answering the question?")
            if g.relevant:
                keep.append(d)
        return {"relevant": keep, "steps": log(state, f"grade: {len(keep)}/{len(state['docs'])} relevant")}

    def after_grade(state: State) -> Literal["answer", "rewrite"]:
        if state["relevant"] or state["rewrites"] >= MAX_REWRITES:
            return "answer"
        return "rewrite"

    def rewrite(state: State):
        q = llm.invoke("Rewrite this question as a better search query for semantic retrieval over "
                       f"documents. Reply with the query only.\nQuestion: {state['question']}\n"
                       f"Previous query that failed: {state['query']}").content.strip()
        return {"query": q, "rewrites": state["rewrites"] + 1, "steps": log(state, f"rewrite: “{q}”")}

    def answer(state: State):
        ctx = state.get("relevant") or []
        if state.get("docs") is None:  # routed away from retrieval
            system = "You are a friendly assistant. Answer briefly."
            context = ""
        elif ctx:
            system = ("Answer using ONLY the numbered context. Cite sources inline like [1], [2]. "
                      "If the context is insufficient, say so.")
            context = "\n\n".join(f"[{i}] ({d.metadata.get('source')}"
                                  f"{', p.' + str(d.metadata['page']) if 'page' in d.metadata else ''})\n"
                                  f"{d.page_content}" for i, d in enumerate(ctx, 1))
        else:
            system = "No relevant documents were found. Say you couldn't find it in the documents; do not guess."
            context = ""
        msgs = [("system", system)] + [(h["role"], h["content"]) for h in state.get("history", [])[-6:]]
        msgs.append(("user", f"{state['question']}\n\nContext:\n{context}" if context else state["question"]))
        return {"answer": llm.invoke(msgs).content, "steps": log(state, "answer: generated")}

    g = StateGraph(State)
    for name, fn in [("route", route), ("retrieve", retrieve), ("grade", grade),
                     ("rewrite", rewrite), ("answer", answer)]:
        g.add_node(name, fn)
    g.add_edge(START, "route")
    g.add_conditional_edges("route", after_route)
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges("grade", after_grade)
    g.add_edge("rewrite", "retrieve")
    g.add_edge("answer", END)
    return g.compile()


def sources_of(docs: list[Document]) -> list[dict]:
    return [{"source": d.metadata.get("source"), "page": d.metadata.get("page"),
             "chunk": d.metadata.get("chunk_index"), "text": d.page_content[:400]} for d in docs]
