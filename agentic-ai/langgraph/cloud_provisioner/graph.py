"""cloud_provisioner -- the LangGraph workflow: chat -> plan -> policy -> cost -> approve -> apply.

    START -> agent <-> tools                       (LLM asks questions, reads catalog/inventory)
               |
               | calls propose_plan / propose_destroy
               v
             plan -> validate -> estimate -> approve -> apply (loops, 1 resource per step) -> report
                        |           |           |                                               |
                        +-----------+-----------+-- problems / rejected: answer the tool call --+--> agent

  The LLM only PROPOSES (a tool call with a structured Plan). Plain code
  validates it, prices it, a human approves it (interrupt), and only then does
  the provider touch the cloud. Every outcome comes back to the LLM as the
  result of its propose_* tool call, so it can fix the plan or explain.

  State is shared with the web UI over AG-UI: phase, plan, cost, issues, actions.
"""

import os

from dotenv import load_dotenv

load_dotenv()

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt
from pydantic import ValidationError

from catalog import KIND_ORDER, Plan, Resource, catalog_text, estimate, ordered
from cloud import Inventory, TransientError, get_provider
from policy import check_budget, check_create, check_destroy

MAX_ATTEMPTS = 3
inventory = Inventory()
provider = get_provider()


class State(MessagesState):
    phase: str                # idle | policy_failed | over_budget | awaiting_approval | rejected | applying | done | failed
    plan: dict | None         # the proposed Plan (+ "destroy": True for teardown)
    cost: dict | None         # estimate(): per-resource and total USD/month
    issues: list[str]         # policy / budget problems of the last proposal
    actions: list[dict]       # apply queue: {op, name, kind, status, attempts, cloud_id, error}
    call_id: str | None       # the propose_* tool call this workflow will answer


# ---- tools the LLM can call ------------------------------------------------

@tool
def list_catalog() -> str:
    """Regions, envs, instance types and monthly prices you can use in a plan."""
    return catalog_text()


@tool
def list_resources(env: str | None = None) -> str:
    """What already exists (optionally only one env: dev, staging or prod)."""
    rows = [f"{n} ({r['kind']}, {r['env']}, {r['region']}) {r['cloud_id']}"
            for n, r in inventory.all().items() if env in (None, r["env"])]
    return "\n".join(rows) or "nothing provisioned"


@tool(args_schema=Plan)
def propose_plan(**plan) -> str:
    """Propose resources to CREATE. The system validates, prices and asks the user to approve, then applies."""
    return "handled by the plan node"


@tool
def propose_destroy(env: str) -> str:
    """Propose deleting EVERYTHING in one env. The user must approve."""
    return "handled by the plan node"


READ_TOOLS = [list_catalog, list_resources]
PROPOSE = {"propose_plan", "propose_destroy"}

SYSTEM = f"""You are a cloud provisioning assistant for AWS-style infrastructure.
Cloud provider in use: {provider.name}.

1. Find out env (dev/staging/prod), region, what the app needs, and a monthly budget if any.
   Ask short questions only for what is missing; pick sensible small defaults otherwise.
2. Call propose_plan with EVERY resource: a vpc, subnets (cidr inside the vpc), security_groups,
   then ec2_instance / rds_instance / s3_bucket. Use depends_on to link each resource to what it
   lives in. Names start with the env, e.g. staging-vpc, staging-web-1.
3. A policy checker and a human approval step run after you propose. If the result lists
   problems, fix them and propose again. Never say something was created unless the result says so.
4. To tear down an env, call propose_destroy.

Catalog:
{catalog_text()}"""


# ---- nodes -----------------------------------------------------------------

def build_graph():
    llm = init_chat_model(os.getenv("MODEL", "litellm:gpt-4o-mini"), temperature=0)
    llm = llm.bind_tools([*READ_TOOLS, propose_plan, propose_destroy])

    def agent(state: State) -> dict:
        return {"messages": [llm.invoke([("system", SYSTEM), *state["messages"]])]}

    def route_agent(state: State) -> str:
        calls = state["messages"][-1].tool_calls
        if not calls:
            return END
        return "plan" if any(c["name"] in PROPOSE for c in calls) else "tools"

    def answer(state: State, text: str) -> ToolMessage:
        """The result of the propose_* call: how the workflow reports back to the LLM."""
        return ToolMessage(text, tool_call_id=state["call_id"])

    def plan(state: State) -> dict:
        """Turn the LLM's tool call into a plan and an action queue (no cloud calls yet)."""
        last: AIMessage = state["messages"][-1]
        call = next(c for c in last.tool_calls if c["name"] in PROPOSE)
        skipped = [ToolMessage("not run: propose alone, in its own step", tool_call_id=c["id"])
                   for c in last.tool_calls if c is not call]
        base = {"call_id": call["id"], "issues": [], "cost": None, "actions": [], "messages": skipped}

        if call["name"] == "propose_destroy":
            env = call["args"]["env"]
            records = {n: r for n, r in inventory.all().items() if r["env"] == env}
            doomed = sorted(records, key=lambda n: KIND_ORDER.index(records[n]["kind"]), reverse=True)
            p = {"env": env, "region": next(iter(records.values()), {}).get("region", "-"), "destroy": True,
                 "resources": [records[n]["spec"] for n in doomed]}
            actions = [{"op": "delete", "name": n, "kind": records[n]["kind"]} for n in doomed]
        else:
            try:
                parsed = Plan.model_validate(call["args"])
            except ValidationError as e:
                return {**base, "plan": None, "phase": "policy_failed", "issues": [str(e)]}
            p = {**parsed.model_dump(), "destroy": False}
            actions = [{"op": "create", "name": r.name, "kind": r.kind} for r in ordered(parsed.resources)]

        for a in actions:
            a.update(status="pending", attempts=0, cloud_id=None, error=None)
        return {**base, "plan": p, "actions": actions, "phase": "checking"}

    def validate(state: State) -> dict:
        p = state["plan"]
        if p is None:  # the tool call did not even parse
            issues = state["issues"]
        elif p["destroy"]:
            issues = check_destroy(p["env"], inventory.all())
        else:
            issues = check_create(Plan.model_validate(p), inventory.all())
        if issues:
            return {"issues": issues, "phase": "policy_failed",
                    "messages": [answer(state, "Policy check failed, nothing was changed:\n- " + "\n- ".join(issues))]}
        return {"issues": []}

    def estimate_cost(state: State) -> dict:
        p = state["plan"]
        parsed = Plan.model_validate(p)
        cost = estimate(parsed)
        if not p["destroy"] and (issues := check_budget(parsed, cost)):
            return {"cost": cost, "issues": issues, "phase": "over_budget",
                    "messages": [answer(state, "Over budget, nothing was changed:\n- " + "\n- ".join(issues))]}
        return {"cost": cost, "phase": "awaiting_approval"}

    def approve(state: State) -> dict:
        """Pause the graph. The checkpointer saves everything; a human resumes it."""
        p, cost = state["plan"], state["cost"]
        verb = "DELETE" if p["destroy"] else "Create"
        money = f"saves about ${cost['total']}/month" if p["destroy"] else f"about ${cost['total']}/month"
        decision = interrupt({
            "message": f"{verb} {len(state['actions'])} resources in {p['env']} ({p['region']}), {money}?",
            "env": p["env"], "destroy": p["destroy"], "total": cost["total"],
        })
        # resolve({"approved": true}) from the UI / CLI; anything else (cancel, reject) is a no
        if isinstance(decision, dict) and decision.get("approved") is True:
            return {"phase": "applying"}
        reason = (decision or {}).get("reason") if isinstance(decision, dict) else None
        return {"phase": "rejected",
                "messages": [answer(state, f"The user rejected the plan{': ' + reason if reason else ''}. Nothing was changed.")]}

    def apply(state: State) -> dict:
        """Do ONE action per step, so the UI sees progress after each and a crash resumes here."""
        actions = [dict(a) for a in state["actions"]]
        a = next(a for a in actions if a["status"] in ("pending", "retrying"))
        p, records = state["plan"], inventory.all()
        a["attempts"] += 1
        try:
            if a["op"] == "create":
                spec = Resource.model_validate(next(r for r in p["resources"] if r["name"] == a["name"]))
                a["cloud_id"] = provider.create(spec, p["env"], p["region"], records)
                inventory.add(spec, p["env"], p["region"], a["cloud_id"])
                a["status"], a["error"] = "ready", None
            else:
                provider.delete(a["name"], records[a["name"]])
                inventory.remove(a["name"])
                a["status"], a["error"] = "deleted", None
        except TransientError as e:
            a["status"] = "retrying" if a["attempts"] < MAX_ATTEMPTS else "failed"
            a["error"] = str(e)
        except Exception as e:  # not worth retrying (bad request, permissions, ...)
            a["status"], a["error"] = "failed", f"{type(e).__name__}: {e}"
        return {"actions": actions}

    def route_apply(state: State) -> str:
        statuses = [a["status"] for a in state["actions"]]
        if "failed" in statuses:
            return "report"  # stop: later resources may depend on the failed one
        return "apply" if any(s in ("pending", "retrying") for s in statuses) else "report"

    def report(state: State) -> dict:
        lines = [f"{a['op']} {a['name']}: {a['status']}"
                 + (f" {a['cloud_id']}" if a["cloud_id"] and a["op"] == "create" else "")
                 + (f" (after {a['attempts']} attempts)" if a["attempts"] > 1 else "")
                 + (f" -- {a['error']}" if a["status"] == "failed" else "")
                 for a in state["actions"]]
        failed = any(a["status"] == "failed" for a in state["actions"])
        head = "FAILED, stopped at the first failure; finished resources are kept:" if failed else "Applied:"
        return {"phase": "failed" if failed else "done",
                "messages": [answer(state, head + "\n" + "\n".join(lines))]}

    def after(next_node: str):
        """validate/estimate/approve: continue, or back to the agent if they answered the call."""
        return lambda state: "agent" if state["phase"] in ("policy_failed", "over_budget", "rejected") else next_node

    g = StateGraph(State)
    g.add_node("agent", agent)
    g.add_node("tools", ToolNode(READ_TOOLS))
    g.add_node("plan", plan)
    g.add_node("validate", validate)
    g.add_node("estimate", estimate_cost)
    g.add_node("approve", approve)
    g.add_node("apply", apply)
    g.add_node("report", report)

    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route_agent, ["tools", "plan", END])
    g.add_edge("tools", "agent")
    g.add_edge("plan", "validate")
    g.add_conditional_edges("validate", after("estimate"), ["estimate", "agent"])
    g.add_conditional_edges("estimate", after("approve"), ["approve", "agent"])
    g.add_conditional_edges("approve", after("apply"), ["apply", "agent"])
    g.add_conditional_edges("apply", route_apply, ["apply", "report"])
    g.add_edge("report", "agent")
    return g
