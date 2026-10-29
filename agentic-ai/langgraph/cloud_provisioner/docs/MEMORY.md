# Agent memory for cloud_provisioner: design

What memory this agent has, what it should add, and where each record lives. Steps 1–4 of the
build plan (section 10) are built: Postgres for the checkpointer and the Store, episodes and
workflow traces recorded at every terminal outcome, and recall of similar past cases. What was
built, and where it differs from the first design, is in section 6 ("As built"). Everything else
here is still design. How the design was reached (questions, reviewed analyses, corrections,
findings while building): [MEMORY_DISCUSSION.md](MEMORY_DISCUSSION.md). For the graph itself see [FLOW.md](FLOW.md); for
the request across services see [ORCHESTRATION.md](ORCHESTRATION.md).

The one rule everything below follows:

> **Memory is data, not authority.** Anything recalled is advice the LLM weighs. It never
> approves a plan, raises a budget or skips a check. `policy.py`, pricing and the human
> approval decide, every time.

## 1. Why memory: every LLM call starts blank

An LLM call remembers nothing. What the agent "knows" in a turn is whatever code puts into the
context window. Memory is the set of stores, plus the rules that decide what goes in and what
gets saved for later.

| Kind | Question it answers | Lifetime | Fills | LangGraph primitive |
|---|---|---|---|---|
| Working | What is happening in this thread? | one thread | messages + graph state | checkpointer |
| Semantic | What is true about this user / tenant? | across threads | a short "known facts" block | Store, keyed or vector-searched |
| Episodic | What happened last time a case like this came up? | across threads | 1–3 past cases | Store, written at outcome points |
| Procedural | How should I do this kind of task? | until changed | system prompt, skills, rules | prompt files, skills, Store |

Finer types you will meet in courses and libraries map onto these four:

| Finer type | Is a kind of | Here |
|---|---|---|
| conversation history, summaries | working / episodic | checkpointer; a summary node if threads grow long |
| semantic cache (reuse an answer for a same-meaning query) | short-term | **not used**: plans depend on inventory, prices, quotas and policy, which change |
| knowledge base, entity memory, persona | semantic | tenant runbooks; user facts |
| workflow memory (execution traces) | procedural evidence | `workflows` namespace, section 6 |
| toolbox memory (find tools by meaning) | procedural | not needed: the agent has 4 tools, all bound every run |
| skills (procedures distilled from repeated successes) | procedural | `skill_drafts` → `procedures`, section 7 |
| shared / coordination memory | working | parent-graph state if a second agent is added |

## 2. How context is assembled each turn

```
 STORES (outlive the call)                 CONTEXT WINDOW FOR ONE LLM CALL
 ┌──────────────────────────┐  run start   ┌────────────────────────────────┐
 │ Procedural               │─────────────▶│ system prompt, tenant procedure│
 │ git + ("procedures",T,A) │              ├────────────────────────────────┤
 ├──────────────────────────┤  key lookup  │ user preferences               │
 │ Semantic                 │─────────────▶│ (defaults, style)              │
 │ ("preferences",T,U) ...  │              ├────────────────────────────────┤
 ├──────────────────────────┤  similarity  │ similar past cases (1–3)       │
 │ Episodic                 │─────────────▶│ request · outcome · reason     │
 │ ("episodes",T,A)         │              ├────────────────────────────────┤
 ├──────────────────────────┤  checkpoint  │ thread: messages, plan, cost,  │
 │ Working                  │─────────────▶│ issues, new message            │
 │ Postgres checkpointer    │              └───────────────┬────────────────┘
 └──────────────────────────┘                              ▼
            ▲                                         LLM call
            └──────────── writes (section 5) ──────────────┘
```

Only working memory is written on every step. The others are written rarely and on purpose,
which keeps them small and trustworthy.

Two read paths, used together:

| | Code injects (a node) | Model searches (a tool) |
|---|---|---|
| Reliability | always runs | the model may not search |
| Cost | tokens every turn | only when used, one extra step |
| Use for | a small high-value set: active procedure, preferences, top 3 cases | deeper lookups: `search_past_cases(query)` |

Google ADK draws the same line with `PreloadMemoryTool` (runs before every LLM request) and
`load_memory` (a tool the model calls).

## 3. Today

| Kind | cloud_provisioner | chat_memory_skills (sibling project) |
|---|---|---|
| Working | Postgres checkpointer + typed state (`plan`, `cost`, `issues`); per-thread run lock in `server.py` | checkpointer |
| Semantic | none | SqliteStore `("memories", user_id)` + sqlite-vec; `save_memory` / `forget_memory` |
| Episodic | **built**: `Episode` in `("episodes", T, A)`, `WorkflowTrace` in `("workflows", T, A)` (Postgres Store + pgvector), recalled by `recall_cases` | none |
| Procedural | system prompt; `policy.py` is **code, not memory** | system prompt + `skills/*/SKILL.md` |

Tenant and user are the run's context (`memory.RequestContext`), set by the server: fixed dev
values (`DEV_TENANT`, `DEV_USER`) until there is auth. `policy.py` still hardcodes one set of rules.

## 4. Namespaces: isolation by namespace, precedence by layer

`T` = tenant, `U` = user, `A` = agent (`"provisioner"`). All three come from authentication,
set by the server in the graph's `context_schema`, **never** from AG-UI state, A2UI actions,
prompt text or tool arguments (the same rule `server.py` applies to state and catalogs today).

| Namespace | Scope | Holds | Written by | Read by |
|---|---|---|---|---|
| *(git)* | platform | base prompt, built-in skills, `policy.py` code | PR + deploy | every run |
| `("policy", T)` | tenant | **typed constraints**: regions per env, required tags, budget caps | admin UI, versioned | **`policy.py`**, on every plan |
| `("procedures", T, A)` | tenant × agent | approved procedure versions + an `:active` pointer | admin activates a draft | prompt, at run start; version pinned in thread state |
| `("skill_drafts", T, A)` | tenant × agent | drafts, their evidence, shadow results | promotion job only | admin UI; **never** the prompt |
| `("workflows", T, A)` | tenant × agent | redacted tool trace, canonical hash, outcome, policy version | graph node, every run | promotion job |
| `("episodes", T, A)` | tenant × agent | code-built outcome records, with `actor_id` | graph node, at outcomes | `recall_cases` node (top 3), `search_past_cases` tool |
| `("knowledge", T)` | tenant | approved runbooks and docs | ingestion | a RAG tool |
| `("preferences", T, U)` | tenant × user | defaults allowed by a kind allowlist | user-confirmed tool | prompt |
| `("fact_drafts", T, U)` | tenant × user | candidate facts + evidence episode ids, confidence, expiry | background worker | the **user** confirms them (tenant facts: an admin); never recalled as drafts |
| `("facts", T, U)` | tenant × user | low-risk personal facts, with provenance | confirmed drafts | `recall` (top 5) |

Platform procedures stay in git: "reviewed and released" is a pull request and a deploy. A
runtime-writable platform namespace would bypass exactly that review.

**`Store.search` matches by prefix.** A search of `("episodes", T)` also returns everything in
`("episodes", T, A, ...)`. Keep sibling scopes as siblings (`(... , "tenant")` next to
`(..., "users", U)`), never one nested inside the other unless the wider read is intended.

### Tenant policy vs tenant procedure

| | Tenant policy (must hold) | Tenant procedure (how to work) |
|---|---|---|
| Example | prod only in us-east-1; owner tag required; budget cap | "propose CloudFront for static sites"; naming tips |
| Stored | `("policy", T)`: typed config | `("procedures", T, A)`: text |
| Enforced by | `policy.py` refuses the plan | the LLM's prompt (advice) |

A rule that must hold is never only prompt text: the LLM can ignore text, it cannot ignore
`policy.py`.

### Precedence

```
platform policy (policy.py code)
  > tenant policy ("policy", T)                      ← both enforced in code
    > tenant active procedure ("procedures", T, A)   ← advice from here down
      > the current validated request / plan
        > user preference ("preferences", T, U)
          > recalled episode or LLM-written lesson
```

A user preference may **narrow** what the tenant allows, never widen it. Example: tenant
policy says prod must be us-east-1; the user's default region is us-west-2. A dev request
defaults to us-west-2; a prod plan in us-west-2 is refused by `policy.py`, whatever the
prompt said.

### Versioned procedures: the version is the key, activation is one write

```python
ns = ("procedures", T, "provisioner")
store.put(ns, "planner:v4", {"text": ..., "status": "approved", "approved_by": admin_id,
                              "approved_at": ..., "source": ["wf-hash-...", "episode-..."]})  # immutable
store.put(ns, "planner:active", {"version": "planner:v4"})   # activate = one put; rollback = put v3
```

Not `filter={"status": "active"}`: activating would then take two writes (retire v3, activate
v4) and the Store has no transaction across them, so a reader in between sees none or two.

## 5. Read and write flows

Two pipelines: a **synchronous** path inside the graph run writes trusted facts and reads recall;
an **asynchronous** path, later and durable, does LLM enrichment and promotion.

```
request → recall → LLM plans → policy / approval / apply → terminal outcome
                                                               │  (in the run, by code)
                                                     episode + workflow trace
                                                               │  (later, a durable worker)
                                          lesson · fact draft · procedure draft → review
```

```
READ, per request
  auth → Ctx(tenant_id, user_id, agent_id)
    → tenant procedure (pinned version) + user preferences + 1–3 episodes   [advice]
    → LLM proposes plan
    → policy.py(platform rules + ("policy", T))                             [the only refusal point]
    → human approval (interrupt)

WRITE, at a terminal outcome (reject · approved · apply_failed · done)
  code builds an Episode from state + the approval payload
    → ("episodes", T, A)     put, idempotent key
    → ("workflows", T, A)    redacted trace + canonical hash
  background promotion job (durable queue, not in-process)
    → ("skill_drafts", T, A) draft + evidence → shadow evaluation
  admin activates
    → ("procedures", T, A) "planner:vN" + "planner:active"
```

When to write, by kind:

| Write path | Latency | Who decides | Used for |
|---|---|---|---|
| hot path (a tool during the turn) | adds to the reply | the model | user preferences the user confirms |
| background (after the thread is idle) | none; appears minutes later | an extraction job | lessons, facts |
| **outcome point** (code, on approve / reject / fail) | none | code: records what actually happened | **episodes, workflow traces** |

What enters the LLM context:

| Memory | Before the LLM call? | Rule |
|---|---|---|
| current checkpoint state | yes, as graph state | this thread only |
| active procedure | yes | the exact approved version, pinned per thread |
| user preferences | yes | may only narrow policy |
| similar episodes | yes, top 1–3 | advice only |
| confirmed facts | yes, bounded | provenance and expiry required |
| workflow traces | **no** | background evidence only; never in streamed state |
| fact drafts, skill drafts / shadow | **no** | not trusted yet |
| inventory, cost, quota, policy | **no: fetched live** | memory may be stale |

Background work survives restarts without an outbox table: the episode carries its own state
(`"enrichment": "pending"`, written in the same `put`), and the worker scans
`store.search(ns, filter={"enrichment": "pending"})` on a schedule. A Store put and an insert into
a separate job table are not one transaction.

> Facts are captured at outcome time. Learning happens later. Procedures need evidence and a
> human to activate them. Only active, bounded, scoped memory reaches the planner.

## 6. Episodes and workflow traces

**Promotion from working memory to episodic memory** is five steps:
trigger → select → distil → merge → index.

1. **Trigger**: an outcome point, not every turn: plan rejected (with reason), approved,
   apply failed, done.
2. **Select**: the request, the final validated `plan` / `cost`, the outcome, the approver's
   reason. Not chit-chat, not intermediate drafts.
3. **Distil**: code fills every factual field. An LLM may add one `lesson` line later, in the
   background. Nothing the model *claims* happened is recorded as fact.
4. **Merge**: before `put`, look for the same case; update a counter instead of a near-duplicate.
5. **Index**: embed only the situation (`request`), so recall matches on the request, not the outcome.

```python
class Episode(BaseModel):
    schema_version: int = 1
    request: str              # redacted: kinds, env, region; not the user's free text (see below)
    env: str; region: str
    resources: list[str]      # kind:name from the plan
    cost_usd: float           # from estimate(), not the LLM
    outcome: Literal["rejected", "approved", "apply_failed", "done"]
    reason: str | None        # approver's text or the error class
    lesson: str | None        # one line, filled later by a background job
    policy_version: str       # rules in force; a pre-change failure must not read as current advice
    actor_id: str             # who asked
    source_thread_id: str; source_checkpoint_id: str
    created_at: str
    retention_state: Literal["active", "suppressed", "deleted"] = "active"

def record_episode(state, runtime: Runtime[Ctx]):
    ns = ("episodes", runtime.context.tenant_id, "provisioner")
    key = f"{thread_id}:{interrupt_id}:{outcome}"          # idempotent: a retry or a double approve writes once
    runtime.store.put(ns, key, ep.model_dump(), index=["request"])
```

- **Idempotent key.** ADK's SQLite memory does the same with `UNIQUE(app, user, session, event)`.
- **Delete = `retention_state`**, not row removal. A rebuild can then skip what a user deleted
  (ADK's in-memory service tracks deleted ids for the same reason).
- **Shared across the tenant, redacted.** A rejection Bob got teaches everyone in the tenant. So
  colleagues see each other's requests in recall. Store the structured fields, not free text,
  or disclose this to users.

**Workflow trace**, one per run (MemoRizz's design): the ordered sequence of
`(tool name, sorted argument keys, error class)` with retries collapsed and values dropped,
hashed with sha256. Two runs with the same hash are the same procedure. The trace also keeps
the policy decision, duration, outcome, resource ids, `thread_id`, `episode_id`, and **no**
secrets or full payloads.

Recall reads the 1–3 closest **active** episodes as a "Similar past cases" block:
request · outcome · reason · lesson. Never replay a past case's tool arguments.

### As built (memory.py, persistence.py)

```
START → recall_cases → agent ⇄ tools                          once per user request; a resume does not re-enter START
          validate │ estimate │ approve │ report  ──outcome──▶ record_outcome → agent
```

| | Built | Changed from the design above, and why |
|---|---|---|
| Backend | `persistence.py`: `AsyncPostgresSaver` + `AsyncPostgresStore` (server), sync ones (CLI, tests); `docker-compose.yml` runs `pgvector/pgvector:pg17` on 127.0.0.1:5434 | Postgres from day one: the dev and production backend are the same. `inventory.db` stays SQLite: it is the provider's state file, not memory |
| Identity | `context_schema=RequestContext(tenant_id, user_id, agent_id, thread_id)`; `server.py` puts it in `config["configurable"]`, which ag-ui-langgraph passes as the context | — |
| Outcomes | private `outcome` state key `{kind, reason}`, set by the node that ended the attempt: `invalid` (tool call didn't parse), `policy_failed`, `over_budget`, `rejected`, `expired`, `policy_changed` (approved, then failed the re-check), `done`, `failed` | finer than `rejected/approved/apply_failed/done`: an expired approval and a plan that changed under the approver are different lessons |
| One record per attempt | `attempt_id` = the `propose_*` tool call id; keys are uuid5 of `tenant:thread:call_id:kind` | keyed on the outcome, not the checkpoint or interrupt: a retried node or a resumed run writes the same key |
| Episode | env, region, op, resource **shapes** (kind, instance_type, engine), cost from `estimate()`, outcome, success, reason, `issue_classes`, actor, thread, `summary` (embedded) | no names, CIDRs or raw args: episodes are shared across the tenant. Policy messages become classes (`public_database`, `open_admin_port`, ...) |
| Workflow trace | separate record: `topology_hash` (per resource: kind, the kinds it depends on, which properties it sets), `signature` (topology + tool sequence + error classes), tool sequence with repeats collapsed, apply error classes, retries; `query` embedded | the topology replaces "sorted argument keys": two plans for the same architecture hash the same whatever their names. Apply errors keep only the leading class (`InsufficientCapacity`) |
| Recall | `store.search(("episodes", T, A), query=<latest user message>, limit=3)` into private `memory_context`; rendered under "ADVICE ONLY" without costs | prices are only ever the live estimate |
| Not streamed | `memory_context` and `outcome` are left out of `PublicState` (the output schema), so they are not in STATE_SNAPSHOT; `server.trusted()` drops any `forwardedProps` key named like a state key (the adapter merges forwardedProps into the graph input, so `outcome` could otherwise forge a record) | — |
| Optional | with no store or context (`demo.py`), both nodes do nothing | — |

Not built yet: `search_past_cases` tool, `lesson` lines, `retention_state` / user deletion,
`policy_version` on episodes, merge of near-duplicates, the `enrichment` state for later
background passes.

Tests (`uv run pytest`, against the `provisioner_test` database with a fake embedding and a
scripted chat model): tenant isolation; one record per outcome however often it is written;
topology equal under renames and different when the architecture differs; names, CIDRs and raw
args never stored; failed, rejected, invalid, over-budget and expired attempts recorded; `done`
is the only success; recall capped at 3 and run once per request; recalled cases never replace
live policy or prices; memory keys absent from the graph output; forwardedProps can't set state.

## 7. Procedural memory: from traces to an active procedure

```
workflows (every run) ──gates──▶ skill_drafts ──shadow──▶ admin activates ──▶ procedures:active
                                                                                  │
                                       demoted on drift ◀── outcome monitoring ◀──┘
```

| Stage | Rule |
|---|---|
| Gates (MemoRizz defaults) | ≥ 5 runs with the same hash, ≥ 80% **business** success, ≥ 2 distinct requests. Frequency alone never promotes: 50 runs at 60% is a bug report. |
| Success | decided by code (approved and applied without error), not "no exception was raised" |
| Distil | an LLM (LangMem `create_prompt_optimizer`, or DSPy GEPA once there is an eval set) writes a **draft**; it never overwrites an active version |
| Shadow | the draft is scored without being injected: replay it on recent recorded requests and compare its plans with what policy and the approver accepted. That costs LLM calls per draft, so it runs once when the draft is created, not on every live request |
| Activate | an admin approves a specific immutable version (section 4) |
| Narrow only | a procedure may add checks, defaults or required fields. A rule whose `kind` would loosen policy, skip approval or raise a budget is refused at write time |
| Demote | when outcomes under the active version drift, roll the pointer back |

Learning is **tenant-scoped**: one tenant's pattern is not a rule for every tenant. A
platform-wide improvement goes through engineering review into git.

**Skills** use the SKILL.md format (as `chat_memory_skills/skills/` does): name + description
in the prompt every turn, body loaded on demand. Platform skills come from files; tenant skills
from `("skills", T)`; on a name clash the platform wins. ADK's `SkillToolset` adds a useful
idea: unload a skill after the turn that used it (`EPHEMERAL`), so skills don't pile up in a
long thread.

## 8. Trust and safety rules

1. **Policy wins.** `policy.py`, pricing and approval run on every plan, whatever memory says.
2. **Scope from auth.** Namespaces use ids from the authenticated session, set in
   `context_schema`. Never from the request body.
3. **Filter before top-k.** Scope is the namespace, so the vector search only ranks the
   caller's records; filtering after ranking can return fewer results or rank on others' data.
4. **Users can see and delete** what is stored about them (`retention_state`).
5. **Procedural writes need a human**; learned rules only narrow behaviour.
6. **Injection persists.** Text from tool results, web pages or documents is never saved as a
   fact or a rule without a person confirming it. Every record carries its source.
7. **Outcomes come from code.** Episodes say what the graph observed.
8. **Write gate.** Only these schemas are accepted: `Episode`, `WorkflowTrace`, `Preference`,
   `SkillDraft`. Anything else is refused.
9. **No semantic cache for plans.** Inventory, prices, quotas and policy change.
10. **Durable jobs.** Promotion and lesson extraction run from a durable queue or job table. An
    in-process queue (LangMem's `LocalReflectionExecutor`) loses pending work on restart.
11. **Expire and cap.** Time-to-live on low-value records; a per-namespace record cap.

## 9. Open-source options

Versions and dates from PyPI, checked 2026-10-28. "Checked" = read in the package source.

| Option | Version, license | What it gives | Gaps | Fit here |
|---|---|---|---|---|
| **LangGraph Store** | ships with langgraph 1.2.18, MIT | namespaced key/value, vector search (`index=`), TTL; InMemory / SQLite / Postgres | no extraction, no access control, no versioning | **the base layer** for every namespace above |
| **LangMem** | 0.0.30 (2025-10-27), MIT | `create_prompt_optimizer` (gradient / metaprompt / prompt_memory), `create_memory_store_manager(schemas=[...])`, `ReflectionExecutor` (debounced per thread) | no release in a year; overwrites prompts in place; in-process queue | borrow: optimizer for **drafts**, schema-driven extraction |
| **deepagents** | 0.7.32 (2026-10-23), MIT | `SkillsMiddleware` (SKILL.md, layered sources), `MemoryMiddleware` (AGENTS.md), `StoreBackend`, `CompositeBackend` | layers are last-wins; its memory prompt invites hot-path self-edits; middleware for `create_agent`, not a custom `StateGraph` | skills on the Store, if adopted |
| **DSPy** | 3.4.1, MIT | offline optimizers: `GEPA`, `MIPROv2`, `SIMBA` | needs an eval set and a metric | procedural drafts, once evals exist |
| **Graphiti** | 0.31.2 (2026-10-20), Apache-2.0 | first-class episodes (`add_episode(..., group_id=)`), temporal entity graph | needs Neo4j / FalkorDB; an LLM call per write | later, for "what changed before X" questions |
| **Mem0** | 2.2.1, Apache-2.0 | per-user fact add / update / delete | its `procedural_memory` mode is a run-history summary, marked for removal in the source | user facts only |
| **Google ADK** | google-adk 2.13.0, Apache-2.0 | sessions with `temp:` / session / `user:` / `app:` state scopes; `MemoryService` (in-memory and SQLite FTS5: raw events, no LLM; Vertex Memory Bank: managed extraction and consolidation); `preload_memory` / `load_memory`; `SkillToolset` | no structured episodes; its own runtime; distilled memory only in the managed service | **ideas**: scope vocabulary, idempotent writes, deletion tracking, the two read tools |
| **MemoRizz** | 0.17.16, **PolyForm Noncommercial 1.0.0**, experimental | the fullest open design of the bootcamp taxonomy: workflow → skill promotion with gates, shadow, activation, demotion; scope before top-k; reversible forgetting | noncommercial license; own runtime (`MemAgent`); no LangGraph integration | **reference only**: reimplement its patterns, don't depend on it |
| **Letta** | 0.34.12, Apache-2.0 | self-editing memory blocks | competes with LangGraph as the runtime | no |
| **Cognee** | 1.6.5, Apache-2.0 | knowledge graphs over documents | closer to RAG than to an outcome ledger | maybe for `("knowledge", T)` |

Many comparison articles are written by vendors of these tools; treat their benchmarks as claims.

## 10. Build plan

| Step | What | Depends on |
|---|---|---|
| — | **built: 1–4** (with Postgres, `expired` / `policy_changed` / `invalid` outcomes, no `search_past_cases` tool yet); see "As built" in section 6 | |
| 0 | move `policy.py` constants into a typed `TenantPolicy`, loaded from `("policy", T)`; one default tenant | — |
| 1 | `context_schema=Ctx(tenant_id, user_id, agent_id)`; `server.py` sets it (fixed dev values until auth) | — |
| 2 | `record_episode` + workflow trace at reject / approved / apply_failed / done; idempotent keys | 1 |
| 3 | `recall_cases` node (top 3, before planning) and `search_past_cases` tool; "Similar past cases" block marked as advice | 2 |
| 4 | tests on isolated copies of the databases: idempotency, tenant isolation, redaction, "recall never bypasses policy" | 2, 3 |
| 5 | background lesson line (durable job) | real episodes to judge it against |
| 6 | promotion: gates → draft → shadow → admin activation → `:active` pointer → demotion | 5, auth (item 2) |
| 7 | housekeeping: reset per-attempt keys (`phase`, ...) at the start of each request; a retention job for old checkpoints (`delete_thread`) | — |

Open questions:

- **Episodes per tenant or per user?** This design shares them across the tenant (redacted).
- **Auth.** Steps 1–4 use fixed dev ids. Real tenant and user ids, thread ownership and approver
  identity are the auth work (item 2).

## 11. Where each layer lives in Postgres

All memory is in **one database** (`provisioner`; tests use `provisioner_test`), split by table
and key. `persistence.py` opens two objects on it, and each owns its tables:

| Layer | Scope | Tables | Keyed by | Written |
|---|---|---|---|---|
| Working (turn) | one request: user message → reply | none of its own: the run's state in process, persisted step by step into the session tables | `thread_id`, `checkpoint_id`, `task_id` | after every step |
| Session (conversation) | one thread, all its turns | `checkpoints`, `checkpoint_blobs`, `checkpoint_writes` (`PostgresSaver`) | `thread_id` | automatically |
| Long-term (cross-session) | every thread of a tenant / user | `store`, `store_vectors` (`PostgresStore`) | `(namespace, key)` | only by code (`record_outcome`) |

### Session tables: the checkpointer

- **`checkpoints`**: one row per step, chained by `parent_checkpoint_id` (resume, replay, fork).
  The `checkpoint` jsonb holds small values inline (`phase`, `call_id`, `expires_at`) and
  `channel_versions`, which says which version of each state key is current.
- **`checkpoint_blobs`**: the larger values (`messages`, `plan`, `cost`, `actions`, `issues`, the
  private `memory_context` / `outcome`, `ag-ui`), msgpack, one row per (key, version). A key gets a
  new blob only when a step changes it. `messages` is stored **whole** each time it changes (251 →
  5029 bytes over 8 versions in one smoke thread), so long threads grow fast: trim or summarise.
- **`checkpoint_writes`**: what each node of a step produced before the next checkpoint, so a
  crashed step resumes without redoing finished nodes. An **approval pause is a row here** on
  channel `__interrupt__` (the approval payload); the answer arrives as `__resume__`.

A **turn is a stretch of the session's chain**, starting at a checkpoint whose metadata says
`source: "input"` (the user's message). A real two-turn test thread:

```
 input  -1                       ← turn 1: user message
 loop 0 recall_cases · 1 agent → propose_plan · 2 plan · 3 validate · 4 estimate
 loop 5 approve (awaiting_approval, __interrupt__ … __resume__) · 6 record_outcome (rejected)
 loop 7 agent → reply · 8 end
 input  9                        ← turn 2: next message; state continues from step 8
 loop 10 recall_cases · 11 agent → reply · 12 end
```

What is **not** stored anywhere: the assembled prompt (system prompt + the rendered "ADVICE ONLY"
cases + messages). `agent()` rebuilds it for every LLM call. Per-turn keys are still state keys,
so they persist with the session until overwritten: `memory_context` is replaced by each turn's
recall and `outcome` is cleared by `record_outcome`, but `phase` carries over into the next
request (e.g. `rejected`). LangGraph has no turn-only scope like ADK's `temp:`; such data must be
cleared by a node or kept out of state.

### Store tables: long-term memory

```
store          prefix 'episodes.<tenant>.provisioner'   key <uuid5>   value jsonb   expires_at / ttl_minutes
store_vectors  (prefix, key, field_name)  → vector(1536), HNSW cosine index, ON DELETE CASCADE from store
```

Namespaces are dotted text prefixes. `search(("episodes", T))` runs
`(prefix = 'episodes.T' OR prefix LIKE 'episodes.T.%')`, so it also returns every sub-namespace:
that is why sibling namespaces need care (section 4). Only indexed fields get a vector row
(`summary` for episodes, `query` for traces).

**Vector search and tenant scope.** A semantic search is
`WHERE prefix … ORDER BY embedding <=> query LIMIT n`, and Postgres can run it two ways:

| Plan | When the planner picks it | Tenant-safe? |
|---|---|---|
| find the tenant's rows by the prefix B-tree, then sort them exactly | the prefix looks selective (the usual case) | yes |
| walk the HNSW index in distance order, then drop rows of other prefixes | the prefix looks broad, or its size is misestimated | **not by default**: pgvector takes the `hnsw.ef_search` (40) nearest candidates across *all* tenants and filters afterwards |

With the second plan, a small tenant whose records are farther from the query than a big
tenant's gets fewer cases than exist, or none: `tests/test_vector_scope.py` forces that plan and
gets **0 of 3**. `persistence.py` therefore opens every Store connection with
`hnsw.iterative_scan = relaxed_order` (pgvector ≥ 0.8, through libpq `options`): the index scan
keeps going until enough rows pass the filter, and the same test gets **3 of 3**. `relaxed_order`
is enough because the Store re-sorts the results by score. The scan stops at
`hnsw.max_scan_tuples` (20 000 by default), so very large tables may need that raised.

**No foreign key joins the two sides.** An episode points to its session only through the
`thread_id` and `attempt_id` copied into it. Deleting a thread keeps its episodes; deleting an
episode keeps the thread.

### One database or two

| | Session tables | Store tables |
|---|---|---|
| Write rate | every step of every run | a few rows per attempt |
| Growth | messages rewritten per change; nothing is deleted today | small records |
| Retention | days–weeks: only active threads need checkpoints | months+: it is the history |
| Needs | fast writes, cleanup (`saver.delete_thread`) | pgvector, backups, per-tenant export and delete |

**Retention: through the APIs, never SQL.** `checkpoints` has no timestamp column (the time is
inside the jsonb), and deleting from it alone would orphan its `checkpoint_blobs` and
`checkpoint_writes` rows. The libraries own those tables, so:

| Need | API |
|---|---|
| delete a whole thread (e.g. for a user deletion request) | `saver.delete_thread(thread_id)`: all three tables |
| shrink a thread that is paused or idle | `saver.prune([thread_id], strategy="keep_latest")`: keeps the checkpoint a resume loads, its pending writes and blobs; one transaction per thread |
| expire long-term records | the Store's `ttl` config (`expires_at`, a background sweep), or `store.delete` |

The checkpointer has no TTL and no way to list threads by age or owner, so choosing which threads
to prune needs the application's own `threads(thread_id, tenant_id, user_id, last_active_at)`
table, the same one thread ownership needs.

**Sharing one connection pool** between the saver and the store works only if the pool's
connections use `autocommit=True, prepare_threshold=0, row_factory=dict_row` (what
`from_conn_string` sets); with `autocommit` alone the saver gets tuples and fails.
`persistence.py` opens each with `from_conn_string` instead.

One database is enough now. Splitting later is configuration, not code: the saver and the store
open their own connections, so `persistence.py` would read `CHECKPOINT_DATABASE_URL` and
`STORE_DATABASE_URL`, falling back to `DATABASE_URL`. Split when the checkpoint write load or
different backup / retention rules call for it.

## Sources

- [LangGraph memory overview](https://docs.langchain.com/oss/python/langgraph/memory) and
  [LangChain memory docs](https://docs.langchain.com/oss/python/memory)
- [DeepLearning.AI: Long-Term Agentic Memory with LangGraph](https://www.deeplearning.ai/short-courses/long-term-agentic-memory-with-langgraph/)
- Package source read for this design: `langmem` 0.0.30, `deepagents` 0.7.32, `mem0ai` 2.2.1,
  `graphiti-core` 0.31.2, `dspy` 3.4.1, `google-adk` 2.13.0, `langgraph-bigtool` 0.0.3
  ([PyPI](https://pypi.org))
- [MemoRizz](https://github.com/RichmondAlake/memorizz): `docs/guides/continual-learning.md`,
  `docs/getting-started/concepts.md`
- Richmond Alake, *AI Memory Management in Agentic Systems* (O'Reilly live bootcamp, day 1):
  the memory-type taxonomy in section 1
