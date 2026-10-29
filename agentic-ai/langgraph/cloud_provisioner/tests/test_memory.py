"""memory.py on its own: records, signatures, privacy, idempotency, recall, tenant isolation."""

import json
import uuid
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage

import memory
from conftest import call
from plans import web_app


def ended(plan, kind, call_id="call-1", reason=None, issues=(), cost=None, actions=(), request="a web app"):
    proposal = call("propose_plan", plan or {}, id=call_id)
    return {"messages": [HumanMessage(request), proposal], "plan": plan and {**plan, "destroy": False},
            "cost": cost, "issues": list(issues), "actions": list(actions), "call_id": call_id,
            "outcome": {"kind": kind, "reason": reason}}


def runtime(ctx, store):
    return SimpleNamespace(context=ctx, store=store)


def test_topology_ignores_names_and_cidrs():
    a = memory.topology(web_app(app="web", net="10.0"))
    b = memory.topology(web_app(app="shop", net="172.16"))
    assert a == b


def test_topology_differs_when_architecture_differs():
    base = memory.topology(web_app())
    assert memory.topology(web_app(db=False)) != base               # one resource fewer
    assert memory.topology(web_app(public_db=True)) != base         # a property set
    rewired = web_app()
    rewired["resources"][4]["depends_on"] = ["staging-web-sg"]     # ec2 no longer in a subnet
    assert memory.topology(rewired) != base


def test_names_cidrs_and_raw_args_never_enter_records(ctx):
    plan = web_app(app="secretproj", net="10.42", public_db=True)
    issues = ["staging-secretproj-db: databases must not be public"]
    episode, trace = memory.build_records(ended(plan, "policy_failed", issues=issues), ctx)
    dumped = json.dumps([episode.model_dump(), trace.model_dump()])
    for leak in ("secretproj", "10.42", "0.0.0.0/0", "443"):
        assert leak not in dumped, leak
    assert episode.issue_classes == ["public_database"]
    assert {"kind": "rds_instance", "instance_type": "db.t3.micro", "engine": "postgres"} in episode.resources


def test_apply_errors_are_classes_not_messages(ctx):
    actions = [{"op": "create", "name": "staging-web-db", "status": "failed", "attempts": 3,
                "error": "InsufficientCapacity: no db.t3.micro capacity in us-east-1 for staging-web-db"}]
    episode, trace = memory.build_records(ended(web_app(), "failed", actions=actions), ctx)
    assert trace.error_classes == ["InsufficientCapacity"] and trace.retries == 2
    assert "staging-web-db" not in json.dumps(trace.model_dump())
    assert episode.success is False


def test_done_is_success_and_trace_is_separate(ctx):
    cost = {"lines": {}, "total": 17.83, "currency": "USD/month"}
    episode, trace = memory.build_records(ended(web_app(), "done", cost=cost), ctx)
    assert episode.success and trace.success and episode.outcome == "done"
    assert trace.episode_id == episode.id and episode.trace_id == trace.id
    assert episode.cost_usd == 17.83
    assert trace.tool_sequence == ["propose_plan"]


def test_tool_sequence_collapses_repeats_and_starts_at_latest_request():
    msgs = [HumanMessage("old"), call("list_catalog", {}), HumanMessage("new"),
            call("list_resources", {}), call("list_resources", {}), call("propose_plan", {})]
    assert memory.tool_sequence(msgs) == ["list_resources", "propose_plan"]


def test_signature_is_stable_for_the_same_workflow(ctx):
    _, t1 = memory.build_records(ended(web_app(app="a", net="10.1"), "done", call_id="x"), ctx)
    _, t2 = memory.build_records(ended(web_app(app="b", net="10.2"), "done", call_id="y"), ctx)
    _, t3 = memory.build_records(ended(web_app(db=False), "done", call_id="z"), ctx)
    assert t1.signature == t2.signature != t3.signature


def test_same_outcome_stores_one_episode(ctx, store):
    state = ended(web_app(), "rejected", reason="too big")
    for _ in range(3):  # a retried node, a resumed run
        memory.record_outcome(state, runtime(ctx, store))
    assert len(store.search(memory.episodes_ns(ctx), limit=10)) == 1
    assert len(store.search(memory.workflows_ns(ctx), limit=10)) == 1


def test_failed_and_rejected_attempts_are_saved(ctx, store):
    rt = runtime(ctx, store)
    memory.record_outcome(ended(web_app(public_db=True), "policy_failed", call_id="c1",
                                issues=["x: databases must not be public"]), rt)
    memory.record_outcome(ended(web_app(), "rejected", call_id="c2", reason="use t3.micro"), rt)
    memory.record_outcome(ended(None, "invalid", call_id="c3", issues=["1 validation error for Plan"]), rt)
    outcomes = sorted(h.value["outcome"] for h in store.search(memory.episodes_ns(ctx), limit=10))
    assert outcomes == ["invalid", "policy_failed", "rejected"]
    assert all(not h.value["success"] for h in store.search(memory.episodes_ns(ctx), limit=10))


def test_record_clears_outcome_and_noops_without_store_or_context(ctx):
    state = ended(web_app(), "done")
    assert memory.record_outcome(state, runtime(None, None)) == {"outcome": None}
    assert memory.recall_cases(state, runtime(ctx, None)) == {"memory_context": []}


def test_tenant_isolation(ctx, store):
    memory.record_outcome(ended(web_app(), "done"), runtime(ctx, store))
    other = ctx.model_copy(update={"tenant_id": f"t-{uuid.uuid4().hex[:8]}"})
    state = {"messages": [HumanMessage("a web app with a postgres database")]}
    assert memory.recall_cases(state, runtime(other, store)) == {"memory_context": []}
    assert len(memory.recall_cases(state, runtime(ctx, store))["memory_context"]) == 1


def test_recall_is_capped_at_three(ctx, store):
    for i in range(5):
        memory.record_outcome(ended(web_app(), "rejected", call_id=f"c{i}", reason=f"no {i}"), runtime(ctx, store))
    state = {"messages": [HumanMessage("create staging web app")]}
    assert len(memory.recall_cases(state, runtime(ctx, store))["memory_context"]) == memory.MAX_CASES == 3


def test_recall_finds_the_similar_case_first(ctx, store):
    rt = runtime(ctx, store)
    memory.record_outcome(ended(web_app(public_db=True), "policy_failed", call_id="db",
                                issues=["x: databases must not be public"]), rt)
    bucket = {"env": "dev", "region": "eu-west-1", "resources": [{"kind": "s3_bucket", "name": "dev-logs"}]}
    memory.record_outcome(ended(bucket, "done", call_id="s3"), rt)
    hits = memory.recall_cases({"messages": [HumanMessage("staging rds_instance postgres database")]}, rt)
    assert hits["memory_context"][0]["issue_classes"] == ["public_database"]


def test_rendered_context_is_advice_without_prices(ctx):
    episode, _ = memory.build_records(ended(web_app(), "rejected", reason="too big",
                                            cost={"lines": {}, "total": 99.5, "currency": "USD/month"}), ctx)
    text = memory.render_memory_context([episode.model_dump()])
    assert "ADVICE ONLY" in text and "rejected" in text and "too big" in text
    assert "$" not in text.split("):", 1)[1] and "99.5" not in text
    assert memory.render_memory_context([]) == ""


def test_policy_messages_map_to_classes():
    assert memory.issue_class("staging-sg: port 22 must not be open to the internet") == "open_admin_port"
    assert memory.issue_class("x: rds_instance must depend on 2 subnets (AWS needs 2 availability zones)") == "rds_two_subnets"
    assert memory.issue_class("x: ec2_instance must depend on a subnet") == "missing_dependency"
    assert memory.issue_class("estimated $40/month is over the $20.0 budget; choose smaller") == "over_budget"
    assert memory.issue_class("something new") == "policy_other"
