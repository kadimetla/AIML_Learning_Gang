"""create_agent isn't just a shortcut for the tool-calling loop -- it
returns an ordinary CompiledStateGraph, so every LangGraph feature used
elsewhere in this repo works on it unchanged: checkpointer=, store=,
interrupt_before=/interrupt_after=, a custom state_schema, etc.

This example wires up two of those knobs that 01_create_agent.py doesn't
touch:
  - system_prompt=       -- built-in instead of a hand-rolled SystemMessage
    (compare to the manual "if not any(isinstance(m, SystemMessage)...)"
    check in ../agent_skills/01_file_based_skill.py)
  - checkpointer= + interrupt_before=["tools"] -- pause before ANY tool
    call for human approval, the same mechanism as ../07_interrupt_before.py,
    just aimed at create_agent's built-in "tools" node instead of a
    hand-written one. Confirmed via agent.get_graph().nodes -- create_agent
    always names its two nodes "model" and "tools".

This only shows the approve path (resume with None, like 07). To reject a
pending tool call you'd need app.update_state(...) to splice in a fake
result or a Command(goto=...) to skip "tools" entirely -- more plumbing than
interrupt_before gives you for free. If you need a clean reject path, drop
to interrupt() called *inside* the tool itself instead, which does support
that directly -- see ../agent_skills/03_script_execution_with_approval.py
and ../hitl/02_approve_or_reject_loop.py for the routing version.

Needs OPENAI_API_KEY in .env (see ../../.env.example) -- the model has to
really decide to call send_email, not follow a script.
"""

from dotenv import load_dotenv

load_dotenv()

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email. This is simulated -- it doesn't actually send anything."""
    return f"email sent to {to} (subject: {subject!r})"


agent = create_agent(
    "openai:gpt-4o-mini",
    tools=[send_email],
    system_prompt="You help draft and send emails. Use send_email once you have to/subject/body.",
    checkpointer=InMemorySaver(),
    interrupt_before=["tools"],
)


if __name__ == "__main__":
    config = {"configurable": {"thread_id": "email-1"}}

    result = agent.invoke(
        {
            "messages": [
                HumanMessage(
                    "Send an email to alice@example.com, subject 'Status', "
                    "body 'All good on my end.'"
                )
            ]
        },
        config=config,
    )
    pending_call = result["messages"][-1].tool_calls[0]
    print(f"paused before tool call: {pending_call['name']}({pending_call['args']})")
    print(f"next node(s): {agent.get_state(config).next}\n")

    # resume with input=None: continues from the checkpoint and actually
    # runs send_email this time, instead of restarting the conversation
    result = agent.invoke(None, config=config)
    for message in result["messages"]:
        label = type(message).__name__
        calls = getattr(message, "tool_calls", None)
        print(f"{label:12s} tool_calls={calls} content={message.content!r}")
