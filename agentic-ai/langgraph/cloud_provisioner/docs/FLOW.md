# How cloud_provisioner works, step by step

The big idea: **the LLM proposes, code decides, a human approves, and only then does the cloud change.**

```
START → agent ⇄ tools                     (talk, read the catalog and inventory)
          │ propose_plan / propose_destroy
          ▼
        plan → validate → estimate → approve ──→ apply ⟲ → report
                  │          │          │                     │
                  └──────────┴──────────┴─ answer the call ───┴──→ agent
```

## 1. The pieces

| Piece | Where | Who decides |
|---|---|---|
| Understand the request and draft a plan | `agent` (`graph.py:104`) | the LLM |
| Look things up | `tools`: `list_catalog`, `list_resources` (`graph.py:54`) | the LLM chooses, code answers |
| Turn the tool call into a plan + action queue | `plan` (`graph.py:117`) | code |
| Guardrails | `validate` → `policy.check_create` / `check_destroy` (`policy.py:16`) | code |
| Price and budget | `estimate` → `catalog.estimate`, `policy.check_budget` | code |
| Go / no-go | `approve` → `interrupt()` (`graph.py:166`) | **a human** |
| Change the cloud | `apply`, one resource per step (`graph.py:182`) | the provider (`cloud.py` / `aws_cloud.py`) |
| Tell the LLM what happened | `report` (`graph.py:211`) | code |

The state (`graph.py:42`) holds `messages` plus the things the UI shows:
`phase`, `plan`, `cost`, `issues` and `actions`.

## 2. A propose tool is a door into the workflow

`propose_plan` has a full Pydantic schema (`Plan` in `catalog.py:44`), so the LLM must fill in
every resource with its kind, name, cidr, ports, instance type and `depends_on`. But **the tool
never runs**. `route_agent` (`graph.py:107`) sees the call and sends the graph to `plan` instead of
`tools`.

Every outcome of the workflow comes back as **the result of that tool call**. `answer()` writes a
`ToolMessage` with the same `tool_call_id`:

| Outcome | The LLM reads |
|---|---|
| policy problems | `Policy check failed, nothing was changed: - staging-sg: port 22 must not be open to the internet` |
| over budget | `Over budget, nothing was changed: ...` |
| human said no | `The user rejected the plan: use t3.micro ... Nothing was changed.` |
| applied | `Applied: create staging-vpc: ready vpc-... ` |

So the LLM fixes its own plan in a normal tool loop, without any special retry logic. In
`demo.py` it fixes four policy problems in one try: a missing cidr, open SSH, and a database
with no security group and only 1 subnet.

## 3. One request, step by step (from `demo.py`)

*"Create a staging env in us-east-1: 2 web servers (t3.small), 443 and SSH open to everyone, a small
postgres I can reach from my laptop. Budget $120/month."*

1. **agent** calls `list_resources(env=staging)` and `list_catalog()`, so **tools** runs and goes back to **agent**.
2. **agent** calls `propose_plan`, which goes to **plan**: 6 actions in dependency order (`catalog.ordered`).
3. **validate** fails. The ToolMessage lists the problems, and the graph goes back to **agent**.
4. **agent** calls `propose_plan` again with the problems fixed. **plan** and **validate** pass, and **estimate** comes to $57.48.
5. **approve** calls `interrupt({...})`. **The graph stops.** The checkpointer saves the state, and the run ends.
6. The human says *no, use t3.micro*. The graph resumes, and `interrupt()` returns `{"approved": false, "reason": ...}`. The rejection goes back to **agent**.
7. **agent** proposes again ($42.30). The human approves.
8. **apply** runs 7 times, once per resource. The database's first try fails (`InsufficientCapacity`, which the fake cloud does on purpose), so its status becomes `retrying`. The next step succeeds.
9. **report** writes the result to the tool call, and **agent** writes the summary for the user.

## 4. Human in the loop: `interrupt()`

```python
decision = interrupt({"message": "Create 7 resources in staging (us-east-1), about $42.3/month?", ...})
```

- The first time it runs, `interrupt()` **raises**. LangGraph saves the state at this node, and the run ends with a pending interrupt.
- To continue, run the graph again on the same `thread_id` with `Command(resume=value)`.
  The `approve` node runs **again from its top**, and this time `interrupt()` **returns** `value`.
- So the code before `interrupt()` in that node must be safe to run twice. Here it only formats a message.
- This needs a checkpointer. The pause can last seconds or days, and it survives a server restart.

The terminal does this in `cli.turn` (`cli.py:29`): it finds `__interrupt__` in the stream, prints the
plan, asks y/N, and calls `app.stream(Command(resume=...))`.

## 5. Why apply does one resource per step

`apply` loops on itself (`route_apply`, `graph.py:205`) instead of creating everything in one node.
1. **Progress:** every step ends with a state update. The CLI prints a line, and the web UI gets a `STATE_SNAPSHOT`, so the plan panel ticks ✓ row by row.
2. **Resume:** every step is checkpointed. If the server dies after 4 of 7 resources, the next run continues at resource 5.
3. **Retries:** a `TransientError` (capacity, throttling) marks the action `retrying`, up to 3 attempts. Any other error is `failed`, and apply stops, because later resources may depend on it.

## 6. Providers and the inventory

`apply` only calls `provider.create(...)` and `provider.delete(...)`. Two classes implement them:

| | `FakeCloud` (`cloud.py:54`) | `AwsCloud` (`aws_cloud.py`) |
|---|---|---|
| select | default | `CLOUD_PROVIDER=aws` |
| vpc / subnet / sg | fake ids, short sleep | `ec2.create_vpc / create_subnet / create_security_group` |
| ec2_instance | fake id | `run_instances` + waiter, AMI from SSM |
| rds_instance | fails once, then ok | `create_db_subnet_group` + `create_db_instance` (Secrets Manager password) |
| s3_bucket | fake id | `create_bucket` + block all public access |

The **inventory** (`inventory.db`) records what was created and its cloud id. It is our version of a
Terraform state file. `list_resources`, destroy and the policy rules (quota, duplicates) all read it.

## 7. The web version: CopilotKit + AG-UI

```
CopilotChat / useAgent / useInterrupt
   │  CopilotKit runtime (web/app/api/copilotkit)  →  HttpAgent
   ▼
POST :8001/agent  (AG-UI over SSE)  →  ag-ui-langgraph LangGraphAgent  →  build_graph()
```

### What each AG-UI event drives in the UI

| AG-UI | From the graph | In the UI (`web/app/page.tsx`) |
|---|---|---|
| `TOOL_CALL_START/ARGS/END`, `TOOL_CALL_RESULT` | `agent` calls a tool; its ToolMessage | a tool card (`useDefaultRenderTool`) |
| `STATE_SNAPSHOT` | state after every node step | **plan panel** via `useAgent().agent.state` |
| `RUN_FINISHED` with `outcome: {type: "interrupt"}` | `approve`'s `interrupt(...)` | **approve card** via `useInterrupt` |
| request with `resume: [{interruptId, status, payload}]` | `Command(resume=payload)` | the card's `resolve({approved: true})` |
| `TEXT_MESSAGE_*` | the agent's final answer | chat bubble |

`server.py` sets `emit_interrupt_outcome=True`. That makes the adapter use the standard AG-UI interrupt
(`RUN_FINISHED.outcome`) and `resume[]`, which CopilotKit's `useInterrupt` handles.

### Captured from a real run (the fake cloud, one dev web server)

Request 1, *"dev env in us-west-2: one t3.micro web server ..."*:

```
RUN_STARTED
STEP agent     TOOL_CALL propose_plan            → 1st plan
STEP plan · STEP validate                        → policy problems, back to agent
STEP agent     TOOL_CALL propose_plan            → fixed plan
STEP plan · STEP validate · STEP estimate
STEP approve
RUN_FINISHED  outcome: { type: "interrupt",
                         interrupts: [{ id: "ef10…", message: "Create 4 resources in dev (us-west-2), about $7.59/month?" }] }
```

Request 2, the same thread, with `resume: [{interruptId: "ef10…", status: "resolved", payload: {approved: true}}]`:

```
RUN_STARTED
STEP approve                       (runs again; interrupt() now returns {approved: true})
STEP apply   STATE_SNAPSHOT ×4     (one snapshot per resource → rows tick ✓)
STEP report
STEP agent   TEXT_MESSAGE_*        (summary)
RUN_FINISHED                       (no outcome = finished normally)
```

`STEP_STARTED apply` appears only once, because the adapter reports node *changes*. The loop still
sends one `STATE_SNAPSHOT` per resource, and that is what the panel listens to.

## 8. Terminal vs web

| | `cli.py` | web |
|---|---|---|
| input | `input()` | `<CopilotChat>` |
| show plan / progress | `show_plan()`, `[apply]` lines | plan panel from `STATE_SNAPSHOT` |
| approval | `ask_human()` → `Command(resume=…)` | approve card → `resolve()` → AG-UI `resume[]` |
| checkpointer | `SqliteSaver` | `AsyncSqliteSaver` (same `checkpoints.db`) |
| graph | `build_graph()` | the same `build_graph()` |

## 9. Teaching points

- **Don't let the LLM act directly on the cloud.** It writes a structured proposal, and everything that matters runs in code you can test.
- **Guardrails are code, not prompt.** The prompt doesn't even list the policy rules. The checker enforces them every time, and the LLM learns from what it rejects.
- **Approval is a graph pause, not a chat message.** Nothing in the conversation can approve a plan. Only a resume value can.
- **Make long work resumable.** Step-sized nodes and a checkpointer give you progress, retries and crash recovery.
- **Hide the provider behind an interface.** Fake for class, LocalStack for integration, AWS for real. The graph doesn't change.
