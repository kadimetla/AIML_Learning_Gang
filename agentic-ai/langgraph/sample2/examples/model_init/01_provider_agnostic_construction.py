"""init_chat_model -- one provider-agnostic constructor, replacing a whole
directory of hand-written provider wrapper functions like
graph_websearch_agent's models/ folder (six files: openai_models.py,
claude_models.py, gemini_models.py, groq_models.py, ollama_models.py,
vllm_models.py -- each reimplementing "build a chat model object").

Requires OPENAI_API_KEY in .env (see .env.example) since this actually
calls a real model.
"""

from dotenv import load_dotenv

load_dotenv()

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage

# "provider:model" string -- infers which integration package to use
model_a = init_chat_model("openai:gpt-4o-mini", temperature=0)

# equivalent: model name and provider as separate arguments
model_b = init_chat_model("gpt-4o-mini", model_provider="openai", temperature=0)

# equivalent again: provider can often be *inferred* from the model name
# alone (gpt-* -> openai, claude-* -> anthropic, gemini-* -> google, ...)
model_c = init_chat_model("gpt-4o-mini", temperature=0)


if __name__ == "__main__":
    for label, model in [("explicit provider:model", model_a), ("provider= kwarg", model_b), ("inferred from name", model_c)]:
        print(f"{label}: {type(model).__name__}(model={model.model_name!r})")

    # all three constructed the exact same kind of object (ChatOpenAI) --
    # and it behaves like any other chat model from here on
    response = model_a.invoke([HumanMessage("Reply with exactly one word: hi")])
    print(f"\nreal call through model_a: {response.content!r}")

    # graph_websearch_agent's Agent.get_llm() is a 6-branch if/elif over
    # server names, each branch importing a different hand-written wrapper
    # class/function. init_chat_model replaces that whole method with one
    # call whose first argument is just a config string.
