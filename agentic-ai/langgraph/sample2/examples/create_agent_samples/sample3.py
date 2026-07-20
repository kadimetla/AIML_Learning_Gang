from typing import TypedDict

from langchain.agents import create_agent
from langgraph.graph import END, START, StateGraph


class WorkflowState(TypedDict):
    topic: str
    draft: str
    review: str


writer = create_agent(
    model="openai:gpt-5.5",
    tools=[],
    system_prompt="Write a short draft.",
)

reviewer = create_agent(
    model="openai:gpt-5.5",
    tools=[],
    system_prompt="Review the draft and suggest improvements.",
)


def write_draft(state: WorkflowState) -> dict:
    result = writer.invoke({
        "messages": [
            {"role": "user", "content": state["topic"]}
        ]
    })
    return {"draft": result["messages"][-1].content}


def review_draft(state: WorkflowState) -> dict:
    result = reviewer.invoke({
        "messages": [
            {"role": "user", "content": state["draft"]}
        ]
    })
    return {"review": result["messages"][-1].content}


builder = StateGraph(WorkflowState)
builder.add_node("write_draft", write_draft)
builder.add_node("review_draft", review_draft)

builder.add_edge(START, "write_draft")
builder.add_edge("write_draft", "review_draft")
builder.add_edge("review_draft", END)

workflow = builder.compile()
