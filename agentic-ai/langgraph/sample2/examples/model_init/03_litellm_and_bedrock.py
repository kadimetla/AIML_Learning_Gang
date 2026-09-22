"""init_chat_model's provider map isn't limited to the openai:/anthropic:/
gemini: strings 01 and 02 use -- confirmed by reading
langchain/chat_models/base.py's provider table directly -- it also knows
"litellm:" (-> langchain_litellm.ChatLiteLLM) and "bedrock_converse:" (->
langchain_aws.ChatBedrockConverse). Same init_chat_model call every other
file in this folder uses, just two more provider strings. Needs
`uv add langchain-litellm langchain-aws` (already added to this project).

litellm is verified for real below: it routes "gpt-4o-mini" straight to
OpenAI using the existing OPENAI_API_KEY, no new credentials needed.

Bedrock is constructed but NOT invoked successfully -- this environment has
no AWS credentials (no AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY, no AWS CLI
configured). Construction itself succeeds without credentials (boto3 builds
its client lazily); only the actual API call fails, with
`NoCredentialsError: Unable to locate credentials` -- confirmed by running
it, not assumed. That's left in place deliberately so this stays honest
about what has and hasn't been verified for real, and so you can see exactly
what to fix (set AWS credentials) to make it work.
"""

from dotenv import load_dotenv

load_dotenv()

from langchain.chat_models import init_chat_model

# --- litellm: a fixed model, verified with a real call ---
litellm_model = init_chat_model("litellm:gpt-4o-mini", temperature=0)

# --- bedrock: a fixed model, construction only ---
bedrock_model = init_chat_model(
    "bedrock_converse:anthropic.claude-3-5-sonnet-20241022-v2:0",
    region_name="us-east-1",
)

# --- the actual "swap to Bedrock at runtime" pattern: same mechanism as
# 02_runtime_configurable_model.py, extended with a third provider.
# region_name has to be in configurable_fields too -- Bedrock needs it, and
# it's simply ignored for providers (openai, litellm) that don't take it.
configurable_model = init_chat_model(
    temperature=0, configurable_fields=("model", "model_provider", "region_name")
)


if __name__ == "__main__":
    result = litellm_model.invoke("Reply with exactly one word: OK")
    print(f"litellm (real call, routed to OpenAI) -> {result.content!r}\n")

    try:
        bedrock_model.invoke("Reply with exactly one word: OK")
    except Exception as e:
        print(f"bedrock direct call -> {type(e).__name__}: {e}\n")

    result = configurable_model.invoke(
        "Reply with exactly one word: OK",
        config={"configurable": {"model": "gpt-4o-mini", "model_provider": "openai"}},
    )
    print(f"configurable -> openai:   {result.content!r}")

    result = configurable_model.invoke(
        "Reply with exactly one word: OK",
        config={"configurable": {"model": "gpt-4o-mini", "model_provider": "litellm"}},
    )
    print(f"configurable -> litellm:  {result.content!r}")

    try:
        configurable_model.invoke(
            "Reply with exactly one word: OK",
            config={
                "configurable": {
                    "model": "anthropic.claude-3-5-sonnet-20241022-v2:0",
                    "model_provider": "bedrock_converse",
                    "region_name": "us-east-1",
                }
            },
        )
    except Exception as e:
        print(f"configurable -> bedrock_converse: {type(e).__name__}: {e}")
