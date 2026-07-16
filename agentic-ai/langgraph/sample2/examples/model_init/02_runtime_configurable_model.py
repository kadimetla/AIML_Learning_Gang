"""init_chat_model(configurable_fields=...) -- pick the provider/model at
invoke() time via config["configurable"], the same mechanism
examples/01_configurable.py used for a plain "title" string. Here it
selects which *model* runs, not just a value a node reads.

Requires OPENAI_API_KEY in .env (see .env.example).
"""

from dotenv import load_dotenv

load_dotenv()

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage

# no model bound yet -- this is a _ConfigurableModel, not a concrete
# ChatOpenAI/ChatAnthropic/etc. The real model is only resolved inside invoke()
configurable_model = init_chat_model(temperature=0, configurable_fields=("model", "model_provider"))


if __name__ == "__main__":
    response = configurable_model.invoke(
        [HumanMessage("Reply with exactly one word: hi")],
        config={"configurable": {"model": "gpt-4o-mini", "model_provider": "openai"}},
    )
    print(f"routed to openai:gpt-4o-mini -> {response.content!r}")

    # same compiled graph/model object, different config -> a different
    # provider entirely (would need ANTHROPIC_API_KEY + langchain-anthropic
    # installed to actually run -- shown here as the shape, not executed)
    #
    # response = configurable_model.invoke(
    #     [HumanMessage("Reply with exactly one word: hi")],
    #     config={"configurable": {"model": "claude-sonnet-5", "model_provider": "anthropic"}},
    # )

    # this is exactly what graph_websearch_agent's per-agent `server`/`model`
    # arguments were trying to achieve by hand (passed into every Agent
    # subclass's __init__, then branched on on in get_llm()) -- except here
    # the choice lives in ordinary invoke() config, not custom constructor
    # arguments threaded through every class in the codebase.
