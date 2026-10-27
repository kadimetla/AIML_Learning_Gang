"""A2UI for cloud_provisioner: the agent describes UI as JSON, the client draws it.

    graph (Python)                         AG-UI                      browser (web_shadcn/)
    ask_details   -> details_form() ----> interrupt value ---------> <A2UISurface> -> shadcn Input/Select/Button
    generate_a2ui -> LLM sub-agent  ----> tool result -------------> <A2UISurface> inline in the chat
                     {"a2ui_operations": [createSurface, updateComponents, updateDataModel]}
    button click  <- {"action": {"name", "context"}} <- resume[] or a user message

The client owns the CATALOG (which component types exist and how they look). It sends the
catalog's schema in RunAgentInput.context; ag-ui-langgraph moves it to state["ag-ui"]["a2ui_schema"].
That is also the switch: no catalog in the request (web/, web_plain/, web_hybrid/, cli.py) means the
A2UI tools are never offered, and those clients keep working as before.

Two uses, on purpose different:
  details_form()  built by CODE: the form that asks for env / region / budget (deterministic)
  generate_a2ui   built by an LLM: read-only views ("show staging as cards")
  approval        NOT A2UI: the approve card is drawn by the client from validated state, so the
                  thing a human signs off on is never LLM-made UI.
"""

from ag_ui_a2ui_toolkit import assemble_ops, resolve_a2ui_catalog
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from catalog import ENVS, REGIONS

# must match web_shadcn/src/a2ui/catalog.tsx (the client sends it back with its schema)
CATALOG_ID = "cloud-provisioner/shadcn/v1"
FORM_SURFACE = "details-form"
SUBMIT = "submit_details"


# For the generate_a2ui sub-agent: one worked example in OUR catalog. Small models otherwise
# list children they never define; a List template over /items avoids hand-numbered ids.
COMPOSITION_GUIDE = """## Example in this catalog (cards for a list of resources)
"components": [
  {"id": "root", "component": "Column", "children": ["title", "list"]},
  {"id": "title", "component": "Text", "variant": "h2", "text": "Staging resources"},
  {"id": "list", "component": "List", "direction": "horizontal", "children": {"componentId": "item", "path": "/items"}},
  {"id": "item", "component": "Card", "child": "item-col"},
  {"id": "item-col", "component": "Column", "children": ["item-name", "item-kind", "item-cost"]},
  {"id": "item-name", "component": "Text", "variant": "h3", "text": {"path": "name"}},
  {"id": "item-kind", "component": "Badge", "variant": "outline", "text": {"path": "kind"}},
  {"id": "item-cost", "component": "KeyValue", "label": "Monthly", "value": {"path": "cost"}}
],
"data": {"items": [{"name": "staging-web-1", "kind": "ec2_instance", "cost": "$7.59"}]}
Every id in child/children must be defined in components. Put repeated rows in data + a List,
never one component per row. Read-only views need no Buttons."""


def enabled(state: dict) -> bool:
    """Did this client send an A2UI catalog? Only then can it render what we send."""
    return bool((state.get("ag-ui") or {}).get("a2ui_schema"))


def catalog_id(state: dict) -> str:
    found = resolve_a2ui_catalog(state)
    return (found and found[1]) or CATALOG_ID


def details_form(args: dict, catalog: str) -> list[dict]:
    """The ask_details form, as A2UI v0.9 operations. Options come from catalog.py, not the LLM;
    the LLM only supplies the question and its best guesses (prefilled values)."""
    options = lambda values: [{"label": v, "value": v} for v in values]
    components = [
        {"id": "root", "component": "Card", "child": "col"},
        {"id": "col", "component": "Column",
         "children": ["title", "question", "env", "region", "budget", "needs", "buttons"]},
        {"id": "title", "component": "Text", "variant": "h3", "text": "A few details"},
        {"id": "question", "component": "Text", "variant": "caption", "text": args.get("question") or ""},
        {"id": "env", "component": "ChoicePicker", "label": "Environment",
         "options": options(ENVS), "value": {"path": "/form/env"}},
        {"id": "region", "component": "ChoicePicker", "label": "Region",
         "options": options(REGIONS), "value": {"path": "/form/region"}},
        {"id": "budget", "component": "TextField", "label": "Monthly budget (USD, optional)",
         "variant": "number", "value": {"path": "/form/budget_usd"}},
        {"id": "needs", "component": "TextField", "label": "What does the app need?",
         "variant": "longText", "value": {"path": "/form/needs"}},
        {"id": "buttons", "component": "Row", "justify": "end", "children": ["cancel", "submit"]},
        {"id": "cancel", "component": "Button", "variant": "secondary", "child": "cancel-text",
         "action": {"event": {"name": "cancel_details"}}},
        {"id": "cancel-text", "component": "Text", "text": "Cancel"},
        {"id": "submit", "component": "Button", "variant": "primary", "child": "submit-text",
         "action": {"event": {"name": SUBMIT, "context": {
             k: {"path": f"/form/{k}"} for k in ("env", "region", "budget_usd", "needs")}}}},
        {"id": "submit-text", "component": "Text", "text": "Continue"},
    ]
    data = {"form": {"env": args.get("env") or "", "region": args.get("region") or "",
                     "budget_usd": "" if args.get("budget_usd") is None else str(args["budget_usd"]),
                     "needs": args.get("needs") or ""}}
    return assemble_ops(intent="create", surface_id=FORM_SURFACE, catalog_id=catalog,
                        components=components, data=data)


class DetailsForm(BaseModel):
    """What the ask_details form may send back. Anything else is refused before the LLM sees it."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    env: str | None = None
    region: str | None = None
    budget_usd: float | None = Field(default=None, ge=0, le=100_000)
    needs: str | None = Field(default=None, max_length=500)

    @field_validator("env", "region")
    @classmethod
    def known(cls, v: str | None, info) -> str | None:
        allowed = ENVS if info.field_name == "env" else REGIONS
        if v is not None and v not in allowed:
            raise ValueError(f"must be one of {allowed}")
        return v


def form_answer(decision) -> str:
    """The resume payload (an A2UI action) -> the text the LLM gets as the tool result.
    The values are user input: validated here, then only passed to the LLM; its next plan
    still goes through policy, pricing and approval."""
    action = decision.get("action") if isinstance(decision, dict) else None
    if not isinstance(action, dict) or action.get("name") != SUBMIT:
        return "The user closed the form without answering. Ask in chat, or pick sensible defaults."
    context = action.get("context")
    filled = {k: v for k, v in (context if isinstance(context, dict) else {}).items() if v not in (None, "")}
    try:
        values = DetailsForm.model_validate(filled)
    except ValidationError as e:
        problems = "; ".join(f"{'.'.join(map(str, err['loc'])) or 'form'}: {err['msg']}" for err in e.errors())
        return f"The form came back with invalid values ({problems}). Call ask_details again."
    return "The user filled in the form: " + values.model_dump_json(exclude_none=True)
