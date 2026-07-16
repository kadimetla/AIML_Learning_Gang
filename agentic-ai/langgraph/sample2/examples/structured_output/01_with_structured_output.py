"""model.with_structured_output(PydanticModel) -- get schema-validated output
straight from the model, instead of prompting "respond in this JSON format"
and hand-parsing the response with json.loads() (as the original
graph_websearch_agent repo does in every one of its "agent" nodes).

Needs a real tool-calling-capable model -- GenericFakeChatModel (used
elsewhere in this project) can't do this, since with_structured_output's
default implementation requires .bind_tools() to be genuinely implemented.
Requires OPENAI_API_KEY in .env (see .env.example).
"""

from dotenv import load_dotenv

load_dotenv()

from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field


class SearchPlan(BaseModel):
    search_term: str = Field(description="the most relevant search term to start with")
    overall_strategy: str = Field(description="the overall strategy to guide the search")
    additional_information: str = Field(
        description="other search terms or filters worth trying"
    )


model = init_chat_model("openai:gpt-4o-mini", temperature=0)
structured_model = model.with_structured_output(SearchPlan)


if __name__ == "__main__":
    result = structured_model.invoke(
        "plan a web search to answer: what is LangGraph and how is it different from LangChain?"
    )
    print(type(result).__name__)
    print(f"  search_term:  {result.search_term!r}")
    print(f"  strategy:     {result.overall_strategy!r}")
    print(f"  extra info:   {result.additional_information!r}")

    # result is a real, validated SearchPlan instance -- not a dict you have
    # to trust the model got the keys right on. Attribute access, not
    # json.loads(response.content)["search_term"] with a try/except around it.
    assert isinstance(result, SearchPlan)
