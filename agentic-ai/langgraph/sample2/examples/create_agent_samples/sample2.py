from dotenv import load_dotenv

load_dotenv()

from typing import TypedDict

from langchain.agents import create_agent
from langgraph.graph import END, START, StateGraph

agent = create_agent(
    model="openai:gpt-5.5",
    tools=[],
    system_prompt="Answer briefly.",
)


class WorkflowState(TypedDict):
    question: str
    answer: str


def call_agent(state: WorkflowState) -> dict:
    result = agent.invoke({
        "messages": [
            {"role": "user", "content": state["question"]}
        ]
    })

    final_message = result["messages"][-1]

    return {
        "answer": final_message.content
    }


builder = StateGraph(WorkflowState)
builder.add_node("call_agent", call_agent)
builder.add_edge(START, "call_agent")
builder.add_edge("call_agent", END)

workflow = builder.compile()


if __name__ == "__main__":
    result = workflow.invoke({"question": "What is the capital of France?"})
    print(f"question={result['question']!r}")
    print(f"answer={result['answer']!r}")
