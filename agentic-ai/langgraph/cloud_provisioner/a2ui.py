"""A2UI for cloud_provisioner: the agent describes UI as JSON, the client draws it.

    graph (Python)                         AG-UI                      browser (web_shadcn/)
    ask_details   -> details_form() ----> interrupt value ---------> <A2UISurface> -> shadcn Input/Select/Button
    generate_a2ui -> LLM sub-agent  ----> tool result -------------> <A2UISurface> inline in the chat
                     {"a2ui_operations": [createSurface, updateComponents, updateDataModel]}
    button click  <- {"action": {"name", "context"}} <- resume[] or a user message

The client owns how components LOOK; the server owns which ones an LLM may USE (VIEW_CATALOG).
The client sends its catalog in RunAgentInput.context; server.py keeps the entry only if it names
our catalog id, and replaces its text with VIEW_SCHEMA_JSON (ag-ui-langgraph then moves it to
state["ag-ui"]["a2ui_schema"]). That is also the switch: no catalog in the request (web/, web_plain/,
web_hybrid/, cli.py) means the A2UI tools are never offered, and those clients work as before.

Two uses, on purpose different:
  details_form()  built by CODE: the form that asks for env / region / budget (deterministic)
  generate_a2ui   built by an LLM: read-only views ("show staging as cards")
  approval        NOT A2UI: the approve card is drawn by the client from validated state, so the
                  thing a human signs off on is never LLM-made UI.
"""

import json
import re

from ag_ui_a2ui_toolkit import assemble_ops, resolve_a2ui_catalog
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from catalog import ENVS, REGIONS

# must match the clients' src/a2ui/catalog.tsx (the client sends it back with its schema)
CATALOG_ID = "cloud-provisioner/shadcn/v1"
FORM_SURFACE = "details-form"
SUBMIT = "submit_details"


# What an LLM-made view (generate_a2ui) may use. The SERVER decides this, not the browser:
# server.py swaps the catalog a client sends for this one, and the toolkit validates every
# generated surface against it (unknown type or missing required prop -> the sub-agent retries).
# Read-only on purpose: no Button and no inputs, so a view can't collect input or send actions.
# The only form is details_form(), built by code. The clients check props again before drawing (Zod).
#
# InventoryTable and PlanCost carry no numbers: the client fills them from the server's inventory and
# the graph's priced plan. A view built from them can't misstate a cost (an LLM's Text can).
_DYN = {"description": 'a string, or {"path": "/..."} bound to the data model'}
_REF = {"type": "string", "format": "componentRef"}
_CHILDREN = {"description": 'ids of child components, or a List template {"componentId", "path"}',
             "format": "componentRefList"}
VIEW_COMPONENTS = {
    "Card": {"description": "bordered box", "properties": {"child": _REF}, "required": ["child"]},
    "Column": {"description": "vertical stack", "properties": {"children": _CHILDREN}, "required": ["children"]},
    "Row": {"description": "horizontal stack",
            "properties": {"children": _CHILDREN, "justify": {"enum": ["start", "center", "end", "spaceBetween"]}},
            "required": ["children"]},
    "List": {"description": "repeat a template over an array in the data model; paths inside are relative to the item",
             "properties": {"children": _CHILDREN, "direction": {"enum": ["vertical", "horizontal"]}},
             "required": ["children"]},
    "Text": {"description": "text; never type costs or counts here, use the components below",
             "properties": {"text": _DYN, "variant": {"enum": ["h1", "h2", "h3", "body", "caption"]}},
             "required": ["text"]},
    "Badge": {"description": "small status label",
              "properties": {"text": _DYN, "variant": {"enum": ["default", "secondary", "outline", "destructive"]}},
              "required": ["text"]},
    "KeyValue": {"description": "one label/value line", "properties": {"label": _DYN, "value": _DYN},
                 "required": ["label", "value"]},
    "Divider": {"description": "separator line", "properties": {}},
    "InventoryTable": {"description": "what exists, from the server's inventory (live). Use this to show resources",
                       "properties": {"env": {"enum": list(ENVS)}}},
    "PlanCost": {"description": "the current plan's resources and monthly cost, priced by the server (live)",
                 "properties": {}},
}
VIEW_CATALOG = {"catalogId": CATALOG_ID, "components": VIEW_COMPONENTS}
VIEW_SCHEMA_JSON = json.dumps(VIEW_CATALOG)  # what the sub-agent is told (state["ag-ui"]["a2ui_schema"])


# For the generate_a2ui sub-agent: worked examples in OUR catalog. Small models otherwise
# list children they never define; a List template over /items avoids hand-numbered ids.
COMPOSITION_GUIDE = """## Examples in this catalog
What exists, or what a plan costs: use the components that read the server, never copied numbers.
"components": [
  {"id": "root", "component": "Card", "child": "col"},
  {"id": "col", "component": "Column", "children": ["title", "table"]},
  {"id": "title", "component": "Text", "variant": "h3", "text": "Staging"},
  {"id": "table", "component": "InventoryTable", "env": "staging"}
]
Cards for a list of things (names and kinds only, no costs): data + a List template.
"components": [
  {"id": "root", "component": "Column", "children": ["title", "list"]},
  {"id": "title", "component": "Text", "variant": "h2", "text": "Staging resources"},
  {"id": "list", "component": "List", "direction": "horizontal", "children": {"componentId": "item", "path": "/items"}},
  {"id": "item", "component": "Card", "child": "item-col"},
  {"id": "item-col", "component": "Column", "children": ["item-name", "item-kind"]},
  {"id": "item-name", "component": "Text", "variant": "h3", "text": {"path": "name"}},
  {"id": "item-kind", "component": "Badge", "variant": "outline", "text": {"path": "kind"}}
],
"data": {"items": [{"name": "staging-web-1", "kind": "ec2_instance"}]}
Every id in child/children must be defined in components. Put repeated rows in data + a List,
never one component per row. There are no Buttons or inputs: views are read-only."""


# A money amount typed by the LLM: "$8", "12 USD", "/month", "per month".
_MONEY = re.compile(r"[$€£]\s?\d|\d\s?(usd|dollars?)\b|/\s?mo(nth)?\b|per month", re.IGNORECASE)


def view_problems(result: str) -> list[str]:
    """Money amounts in an LLM-made view (component text or its data model). The toolkit's
    validator checks structure, not content; costs must come from PlanCost, never typed text."""
    try:
        ops = json.loads(result).get("a2ui_operations")
    except (TypeError, ValueError, AttributeError):
        return []
    found: list[str] = []

    def walk(v, where: str):
        if isinstance(v, str) and _MONEY.search(v):
            found.append(f"{where}: {v[:60]!r}")
        elif isinstance(v, dict):
            for k, x in v.items():
                if k != "path":  # a binding, not text
                    walk(x, where)
        elif isinstance(v, list):
            for x in v:
                walk(x, where)

    for op in ops if isinstance(ops, list) else []:
        for c in ((op.get("updateComponents") or {}).get("components") or []) if isinstance(op, dict) else []:
            if isinstance(c, dict):
                walk({k: v for k, v in c.items() if k not in ("id", "component")}, str(c.get("id")))
        if isinstance(op, dict) and isinstance(op.get("updateDataModel"), dict):
            walk(op["updateDataModel"].get("value"), "data")
    return found


def rejected(problems: list[str]) -> str:
    """The tool result instead of a view that typed money amounts: the client shows nothing, the agent retries."""
    return json.dumps({"error": "view_rejected", "message": (
        f"This view was not shown: it typed money amounts ({'; '.join(problems[:3])}). Costs come only from "
        "the PlanCost component, resources from InventoryTable. Call generate_a2ui again using those, "
        "with no amounts in any text or data.")})


def enabled(state: dict) -> bool:
    """Did this client send our A2UI catalog? Only then can it render what we send.
    (server.py drops any other catalog, and puts VIEW_SCHEMA_JSON in place of ours.)"""
    return bool((state.get("ag-ui") or {}).get("a2ui_schema"))


def server_catalog(sent: str) -> str | None:
    """The client's catalog entry -> what the sub-agent is told: ours if the client renders our
    catalog id, else None (no A2UI on this run). The client's own text never reaches the LLM."""
    try:
        sent_id = json.loads(sent).get("catalogId")
    except (TypeError, ValueError, AttributeError):
        return None
    return VIEW_SCHEMA_JSON if sent_id == CATALOG_ID else None


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
