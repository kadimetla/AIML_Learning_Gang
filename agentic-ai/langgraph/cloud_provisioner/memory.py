"""Long-term memory: what happened to earlier proposals, so the next plan can avoid repeats.

    START -> recall_cases -> agent ...                  once per user request, not per tool loop
    validate / estimate / approve / report
          -- terminal outcome --> record_outcome -> agent
                                   ├─ Episode       ("episodes", tenant, agent)   recalled as advice
                                   └─ WorkflowTrace ("workflows", tenant, agent)  evidence for later learning

Every record is built by CODE from validated state: the plan that passed (or failed) policy, the
priced cost, the approver's decision, the apply results. Nothing the LLM says is recorded as fact.
No LLM calls, no A2UI, no approval logic here. Design and the reasons: docs/MEMORY.md.

Recalled cases are ADVICE in the prompt. They never decide anything: policy, prices and the
inventory are always read live, and every plan still goes through policy and a human.

tenant_id / user_id come from the server (RequestContext), never from the browser.
"""

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime
from pydantic import BaseModel, ConfigDict

MAX_CASES = 3
SCHEMA_VERSION = 1
INDEXED = ["summary", "query"]  # the only embedded fields: an episode's summary, a trace's query
_IDS = uuid.UUID("5d2b8f7e-0c1a-4f53-9a57-8a8f3c1e0d42")  # namespace for deterministic record ids


class RequestContext(BaseModel):
    """Who is asking, set by the server per request (LangGraph's context_schema).
    ag-ui-langgraph passes the server's config["configurable"] (plus thread_id) as the context."""
    model_config = ConfigDict(extra="ignore", frozen=True)
    tenant_id: str
    user_id: str
    agent_id: str = "provisioner"
    thread_id: str


def episodes_ns(ctx: RequestContext) -> tuple[str, ...]:
    return ("episodes", ctx.tenant_id, ctx.agent_id)


def workflows_ns(ctx: RequestContext) -> tuple[str, ...]:
    return ("workflows", ctx.tenant_id, ctx.agent_id)


Outcome = Literal["invalid", "policy_failed", "over_budget", "rejected", "expired",
                  "policy_changed", "done", "failed"]


class Episode(BaseModel):
    """One proposal and how it ended. Shared within the tenant, so no names, CIDRs or raw args."""
    schema_version: int = SCHEMA_VERSION
    id: str
    attempt_id: str              # the propose_* tool call this proposal answered
    thread_id: str
    actor_id: str
    summary: str                 # the embedded text: what was proposed and how it ended
    op: Literal["create", "destroy"] | None
    env: str | None
    region: str | None
    resources: list[dict]        # {"kind", "instance_type"?, "engine"?}: shape, not identity
    cost_usd: float | None       # estimate() at the time; a recalled case never shows it as current
    outcome: Outcome
    success: bool
    reason: str | None           # the approver's words (trimmed) or the first error class
    issue_classes: list[str]     # normalised policy / budget problems, e.g. "public_database"
    trace_id: str
    created_at: str


class WorkflowTrace(BaseModel):
    """The same attempt as evidence for learning: shapes and classes only, never values."""
    schema_version: int = SCHEMA_VERSION
    id: str
    episode_id: str
    query: str                   # embedded: the episode summary without the outcome
    topology_hash: str           # resource kinds, dependency kinds, property keys
    signature: str               # topology + tool sequence + error classes
    tool_sequence: list[str]     # tool names this attempt, consecutive repeats collapsed
    error_classes: list[str]
    retries: int                 # extra apply attempts (transient errors)
    outcome: Outcome
    success: bool
    created_at: str


# ---- normalising what happened into classes ----------------------------------------

# policy.py / check_budget messages -> a stable class. Order matters: first match wins.
ISSUE_CLASSES = [
    (r"is not allowed; use one of", "region_not_allowed"),
    (r"plan has no resources", "empty_plan"),
    (r"is used twice", "duplicate_name"),
    (r"name must start with", "name_prefix"),
    (r"already exists", "already_exists"),
    (r"depends on unknown resource", "unknown_dependency"),
    (r"needs a cidr", "missing_cidr"),
    (r"must depend on 2 subnets", "rds_two_subnets"),
    (r"must depend on a ", "missing_dependency"),
    (r"must not be open to the internet", "open_admin_port"),
    (r"instance_type must be one of", "bad_instance_type"),
    (r"engine must be", "bad_engine"),
    (r"databases must not be public", "public_database"),
    (r"buckets must not be public", "public_bucket"),
    (r"^quota:", "ec2_quota"),
    (r"over the \$[\d.]+ budget", "over_budget"),
    (r"destroying prod is not allowed", "prod_destroy"),
    (r"nothing to destroy", "nothing_to_destroy"),
    (r"validation error", "invalid_plan"),
]


def issue_class(issue: str) -> str:
    return next((c for pattern, c in ISSUE_CLASSES if re.search(pattern, issue)), "policy_other")


def error_class(error: str | None) -> str:
    """An apply error -> its leading identifier ("InsufficientCapacity: no t3.small ..." ->
    "InsufficientCapacity"), never the message (it can carry names, ids, regions)."""
    m = re.match(r"\s*([A-Za-z][A-Za-z0-9_.]*)\s*:", error or "")
    return m.group(1).rsplit(".", 1)[-1] if m else "error"


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def resource_shapes(plan: dict) -> list[dict]:
    keep = ("instance_type", "engine")
    return sorted(({"kind": r["kind"], **{k: r[k] for k in keep if r.get(k)}} for r in plan.get("resources", [])),
                  key=lambda s: json.dumps(s, sort_keys=True))


def topology(plan: dict) -> list[list]:
    """The architecture, without identity: per resource its kind, the kinds it depends on, and
    which properties it sets (keys, not values; `public: false` is the default and not a key).
    Two plans for the same shape of app hash the same whatever their names or CIDRs are."""
    kinds = {r["name"]: r["kind"] for r in plan.get("resources", [])}
    rows = []
    for r in plan.get("resources", []):
        set_keys = sorted(k for k, v in r.items()
                          if k not in ("kind", "name", "depends_on") and v not in (None, False, [], ""))
        rows.append([r["kind"], sorted(kinds.get(d, "existing") for d in r.get("depends_on", [])), set_keys])
    return sorted(rows, key=json.dumps)


def tool_sequence(messages: list) -> list[str]:
    """Tool calls since the latest user message, consecutive repeats collapsed (retries)."""
    start = max((i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=-1)
    names = [c["name"] for m in messages[start + 1:] if isinstance(m, AIMessage) for c in m.tool_calls]
    return [n for i, n in enumerate(names) if i == 0 or names[i - 1] != n]


def latest_request(messages: list) -> str:
    return next((m.text for m in reversed(messages) if isinstance(m, HumanMessage)), "")


# ---- building the records ----------------------------------------------------------

def _one_line(text: str | None, limit: int = 200) -> str | None:
    return " ".join(text.split())[:limit] if text else None


def describe(plan: dict | None) -> str:
    if not plan:
        return "an invalid plan"
    counts: dict[str, int] = {}
    for s in resource_shapes(plan):
        label = " ".join(filter(None, [s["kind"], s.get("instance_type"), s.get("engine")]))
        counts[label] = counts.get(label, 0) + 1
    parts = ", ".join(f"{n} {label}" if n > 1 else label for label, n in counts.items())
    op = "destroy" if plan.get("destroy") else "create"
    return f"{op} {plan.get('env')} in {plan.get('region')}: {parts or 'no resources'}"


def build_records(state: dict, ctx: RequestContext, now: datetime | None = None) -> tuple[Episode, WorkflowTrace]:
    """The episode and the trace for the attempt that just ended (state["outcome"] is set)."""
    outcome = state["outcome"]
    kind: Outcome = outcome["kind"]
    plan, cost = state.get("plan"), state.get("cost")
    actions = state.get("actions") or []
    created = (now or datetime.now(UTC)).isoformat(timespec="seconds")

    issues = [issue_class(i) for i in state.get("issues") or []]
    errors = [error_class(a.get("error")) for a in actions if a.get("status") == "failed"]
    reason = _one_line(outcome.get("reason")) or (errors[0] if errors else None) or (issues[0] if issues else None)

    # deterministic ids: a retried or resumed run writes the same keys, so one record per attempt
    key = f"{ctx.tenant_id}:{ctx.thread_id}:{state.get('call_id')}:{kind}"
    episode_id = str(uuid.uuid5(_IDS, "episode:" + key))
    trace_id = str(uuid.uuid5(_IDS, "trace:" + key))

    what = describe(plan)
    ending = kind.replace("_", " ") + (f" ({reason})" if reason else "")
    episode = Episode(
        id=episode_id, attempt_id=state.get("call_id") or "", thread_id=ctx.thread_id, actor_id=ctx.user_id,
        summary=f"{what}. Outcome: {ending}.",
        op=("destroy" if plan.get("destroy") else "create") if plan else None,
        env=plan.get("env") if plan else None, region=plan.get("region") if plan else None,
        resources=resource_shapes(plan) if plan else [],
        cost_usd=cost["total"] if cost else None,
        outcome=kind, success=kind == "done", reason=reason,
        issue_classes=sorted(set(issues)), trace_id=trace_id, created_at=created)

    topo_hash = _sha(topology(plan)) if plan else _sha(None)
    tools = tool_sequence(state.get("messages") or [])
    error_classes = sorted(set(issues + errors))
    trace = WorkflowTrace(
        id=trace_id, episode_id=episode_id, query=what, topology_hash=topo_hash,
        signature=_sha([topo_hash, tools, error_classes]), tool_sequence=tools, error_classes=error_classes,
        retries=sum(max(0, a.get("attempts", 0) - 1) for a in actions),
        outcome=kind, success=kind == "done", created_at=created)
    return episode, trace


# ---- the two graph nodes -------------------------------------------------------------
# Sync on purpose: they run in cli.py's sync graph and, in a worker thread, in server.py's async
# one (the async Postgres store accepts sync calls from other threads).

def recall_cases(state: dict, runtime: Runtime[RequestContext]) -> dict:
    """Up to MAX_CASES similar past attempts from this tenant, for the agent's prompt."""
    ctx, store = runtime.context, runtime.store
    query = latest_request(state.get("messages") or [])
    if ctx is None or store is None or not query:
        return {"memory_context": []}
    hits = store.search(episodes_ns(ctx), query=query, limit=MAX_CASES)
    return {"memory_context": [h.value for h in hits][:MAX_CASES]}


def record_outcome(state: dict, runtime: Runtime[RequestContext]) -> dict:
    """Write the episode and trace of the attempt that just ended, once (idempotent keys)."""
    ctx, store = runtime.context, runtime.store
    if state.get("outcome") and ctx is not None and store is not None:
        episode, trace = build_records(state, ctx)
        store.put(episodes_ns(ctx), episode.id, episode.model_dump(), index=["summary"])
        store.put(workflows_ns(ctx), trace.id, trace.model_dump(), index=["query"])
    return {"outcome": None}


def render_memory_context(cases: list[dict]) -> str:
    """The prompt block. Costs are left out on purpose: prices are only ever the live estimate."""
    if not cases:
        return ""
    lines = []
    for c in cases[:MAX_CASES]:
        what = describe({"env": c.get("env"), "region": c.get("region"), "resources": c.get("resources") or [],
                         "destroy": c.get("op") == "destroy"}) if c.get("op") else "an invalid plan"
        why = f': "{c["reason"]}"' if c.get("reason") else ""
        lines.append(f"- {c.get('created_at', '')[:10]} · {what} · {c.get('outcome', '').replace('_', ' ')}{why}")
    return ("\n\nSimilar past proposals in this team (ADVICE ONLY: they approve nothing; policy, prices and "
            "the inventory are checked live on every plan, and a human still approves):\n" + "\n".join(lines))
