# Agent memory: the discussion record

How the memory design in [MEMORY.md](MEMORY.md) was reached, one question at a time: what was
asked, what the answer found, which outside analyses were reviewed and what was corrected in
them, and what came up while building it. MEMORY.md is the result. This file shows the reasons.

Package versions are the ones read in October 2026; "read in source" means the installed package
code was checked, not only its docs.

## Decisions at a glance

| # | Decision | Why | Where discussed |
|---|---|---|---|
| D1 | The LangGraph Store is the memory ledger; libraries only help around it | already in use; namespaced, searchable, swappable backends; no second storage system | §1, §5, §6 |
| D2 | **Memory is data, not authority**: recall is advice, `policy.py`, live prices and the human decide | memory persists across sessions, so one bad or injected record would affect every later run | §2, §4, §7 |
| D3 | Episodes are written **by code at outcome points**, not by the LLM | the graph knows exactly when and how a proposal ended; true by construction | §2, §4 |
| D4 | Procedural changes are **drafts** a person activates; learned rules only narrow | a rewritten prompt that goes live unreviewed is the riskiest write | §3, §4, §6 |
| D5 | MemoRizz is a **reference only** | PolyForm Noncommercial license; own runtime; experimental | §6, §7 |
| D6 | Namespaces isolate, layers set precedence; ids from auth via `context_schema` | the Store has no access control; namespaces are only paths | §3, §9, §10 |
| D7 | Tenant **constraints** go in `policy.py` (typed `("policy", T)`), not procedure text | the LLM can ignore text; it cannot ignore code | §10 |
| D8 | A version is part of the **key**; activation is one write to an `:active` pointer | no transaction across two Store writes | §10 |
| D9 | Episodes are **shared across the tenant**, redacted; preferences are per user | a rejection one person got should teach the team; colleagues must not see each other's free text | §9, §10 |
| D10 | Idempotency keyed on the **outcome**, not the checkpoint | a resume after a crash gets a new checkpoint id and would duplicate the record | §9, §12 |
| D11 | Traces never go into streamed graph state | AG-UI sends state to the browser in every STATE_SNAPSHOT | §12 |
| D12 | No outbox table: the episode carries its own `enrichment` state | a Store put and an outbox insert are not one transaction | §12 |
| D13 | User facts are confirmed **by the user**; tenant facts by an admin | an admin reviewing someone's personal profile is the wrong reviewer | §12 |
| D14 | Postgres (checkpointer + Store, pgvector) from day one | dev should mirror production | §13 |
| D15 | Recall once per user request; one record per planning attempt; episode and trace separate; trace hashes the **topology** | tool loops would re-run retrieval; rejected attempts are evidence; names must not change the hash | §13 |
| D16 | `forwardedProps` named like a state key are dropped | ag-ui-langgraph merges them into the graph input: a prop `outcome` could forge a record | §14 |
| D17 | One Postgres database, separate tables per layer; split into two databases only by configuration, later | session tables are high-write and short-lived, Store tables small and long-lived | §16, §17 |
| D18 | Application tables only for what the libraries can't hold: `threads` (ownership, retention) and an append-only `audit_events`; no jobs table yet, and no SQL on LangGraph-owned tables | a jobs table can't commit with a Store put; checkpoints are keyed by thread only | §18 |
| D19 | Store connections run with `hnsw.iterative_scan = relaxed_order` | an HNSW-driven plan filters tenants *after* taking the 40 nearest candidates; a small tenant got 0 of 3 cases | §19 |

---

## 1. Which open-source memory would be best?

> "for memory what opensource would be best - working, semantic, procedural etc. we can deep dive into kind of memories"

**The four kinds**, from cognitive science and used by the LangGraph docs:

| Kind | Holds | Written | Read | Main risk |
|---|---|---|---|---|
| Working | the thread: messages, tool results, state | every step | every step | too long for the context window |
| Semantic | facts ("prefers us-east-1") | extracted from chats | by relevance | stale or conflicting facts |
| Episodic | what happened ("rejected a plan on Oct 27 because of S3") | after a decision | "have we done this before?" | volume, privacy, over-reading one case |
| Procedural | how to act: prompts, rules, skills | rarely, deliberately | at start-up | a bad or injected rule quietly changes behaviour |

At that point `chat_memory_skills` had working memory (checkpointer), semantic memory (SqliteStore
+ sqlite-vec, `("memories", user_id)`, written by the model with `save_memory`) and hand-written
skills. `cloud_provisioner` had only the checkpointer and graph state.

**Options compared:** LangGraph Store (MIT, native), LangMem (MIT, no release since Oct 2025),
Mem0 (Apache-2.0, per-user facts), Graphiti (Apache-2.0, facts with valid-from/to, needs a graph
database), Letta (a whole runtime that competes with LangGraph), Cognee (knowledge graphs over
documents, closer to RAG). Most "best memory framework" articles are written by these vendors.

**Recommendation:** keep the checkpointer and trim long threads; keep the Store for facts but make
writes deliberate (background extraction, one key per fact); Graphiti only for facts that change
over time; **build episodic memory on the Store for cloud_provisioner** (the graph already has the
outcome points); procedural memory only as suggestions a person accepts, always beneath policy.
Skip Letta.

## 2. When and why each kind, and how it reaches the context

> "when and why we need each and how are they used by the agents to enable context"

Every LLM call starts blank; memory is how code decides what goes into the window.

```
 procedural ─► system prompt, rules, skills index        loaded at start-up
 semantic   ─► "Known about this user: ..." (top-k)       searched each turn
 episodic   ─► "Similar past case: ..." (top 1–3)         searched when deciding
 working    ─► this thread's messages + state             always, trimmed
```

| Your agent… | Add |
|---|---|
| answers one-off questions | working memory only |
| has multi-step tasks or pauses for a person | a checkpointer |
| has returning users | semantic |
| makes decisions people correct or approve | **episodic** |
| should improve its working style | procedural, with a person approving |
| has long threads | trim or summarise *before* adding more memory |

Two choices that apply to every kind:

- **Code reads vs the model reads.** A node injecting a small top-k is predictable; a search tool
  is cheaper but the model may not look. Common mix: inject a little, offer a tool for more.
- **Where writes happen.** Hot path (the model calls a tool) is immediate but costs attention;
  background is better quality and can merge duplicates. Episodes are best written by code at
  outcome points; procedural rules in the background with a person approving.

This was captured as the Claude Doc "Agent Memory for LangGraph Agents", later turned into the
repo's MEMORY.md and the `chat_memory_skills/docs/slides.html` lesson.

## 3. Procedural memory: tenants, users, skills

> "deep dive into procedure memory what it is implemented. how is it used for per tenant vs tenant and user of the tenant and skills etc how are they stored and when"

Procedural memory is **layered**: platform → tenant → (team/role) → user → thread. A more
specific layer may customise or narrow, never loosen.

| Layer | Writer | May change | Stored | Written |
|---|---|---|---|---|
| Platform | engineers | everything | git | PR + deploy |
| Tenant | admin, or an approved proposal | add skills and checks, set defaults | Store, per tenant | admin UI / approval |
| User | the user | style and defaults only | Store, per tenant × user | a `save_preference` tool |
| Thread | nobody | this conversation | checkpoint | every step |

- `policy.py`, pricing and approval are **code, not memory**: enforced after the model.
- **Prefix search** (`Store.search` matches namespace prefixes) means tenant and user rules must be
  siblings, or a tenant search returns every user's rules.
- Rules are **versioned, never edited in place**; `kind` is an allowlist per layer (a user-level
  "skip approval" has no kind that admits it).
- Read at three points: resolve the effective set at run start (with headers stating each block's
  rank), skill catalog every call (names only), skill body on demand. **Pin versions per thread**,
  so an approval resumed tomorrow runs under the rules the plan was made with.
- Anything read from a tool result, web page or document is **never** saved as a rule.

## 4. What the LangGraph Store is

> "what is lang graph store"

The Store is LangGraph's long-term key-value store, next to the checkpointer:

| | Checkpointer | Store |
|---|---|---|
| Holds | one thread's state at every step | whatever code saves |
| Keyed by | `thread_id` | `(namespace tuple, key)` |
| Written | automatically after every step | only on `put` |
| Lifetime | the thread | across threads and users |

`put / get / delete / search(ns_prefix, query=, filter=, limit=) / list_namespaces`, async
variants, an `index={"dims", "embed", "fields"}` config for vector search, TTLs. Backends:
InMemory, SQLite, Postgres. What it does **not** do: extract or merge facts, access control
(namespaces are only paths), or versioning (`put` overwrites).

## 5. What LangGraph and LangMem actually implement

> "can we deep dive and understand what it implements for procedural memory. how working memory is promoted to episodic memory."

Read in the LangGraph docs and the LangMem 0.0.30 source:

- **LangGraph:** procedural memory is a documented *pattern* ("reflection"): one Store key holds
  the prompt and a node overwrites it. No history, no review.
- **LangMem:** `create_prompt_optimizer` (`gradient`, `metaprompt`, `prompt_memory`) returns a new
  prompt string; its bundled reflection graph overwrites it in place. `create_memory_store_manager`
  has an LLM insert/update records. `ReflectionExecutor` debounces one job per thread; the local
  one keeps jobs in memory, so a restart loses them.
- **Missing everywhere:** versioned keys, draft → active review, layers, rollback, audit. So the
  optimizer may only write **drafts**.

**Working → episodic promotion** is five steps: **trigger** (an outcome point, not every turn) →
**select** (request, final validated plan/cost, outcome, the human's reason) → **distil** (code
fills the facts; an LLM may add one lesson line later) → **merge** (update a counter rather than
add a near-duplicate; that counter is also the signal for a procedural rule) → **index** (embed
the situation, not the outcome).

```
checkpoint (every step) ──outcome──► episode ──same lesson ≥3×──► draft rule ──human──► active
```

Each step up writes less, less often, and needs more trust.

## 6. Options that can be adapted readily

> "what are the available options that can be readily adapted for the purpose"

Read in each package's latest source:

| Option | Ready to use | Missing | Fit |
|---|---|---|---|
| **deepagents** 0.7.32 | `SkillsMiddleware` (layered SKILL.md sources), `MemoryMiddleware`, `StoreBackend`, `CompositeBackend` | layers are last-wins; its memory prompt invites hot-path self-edits; middleware for `create_agent` | best ready-made fit for skills (platform source last so it can't be overridden) |
| **LangMem** 0.0.30 | prompt optimizer, memory manager, reflection executor | stale; overwrites in place | the optimizer for drafts |
| **DSPy** 3.4.1 | offline optimizers (GEPA, MIPROv2, SIMBA) | needs an eval set and metric | procedural drafts, once evals exist |
| **Graphiti** 0.31.2 | first-class episodes, `group_id` per tenant, temporal facts | graph database; an LLM call per write | later, for "what changed before X" |
| **Mem0** 2.2.1 | per-user facts | its `procedural_memory` is a run-history summary, marked for removal in the source | user facts only |
| **Letta**, **MIRIX / MemOS** | own runtimes / servers | compete with LangGraph | no |
| **Own code on the Store** | exactly our schema and triggers | ~100 lines to write | **best for episodes** |

## 7. MemoRizz and the O'Reilly memory bootcamp

> "https://github.com/kadimetla/memorizz … AI Memory Management Bootcamp (Day 1) … can we deep to understand opensource available options to use with langgraph memory concepts how build along with tools"

The bootcamp (Richmond Alake) splits memory more finely and treats the **memory unit** (schema)
and **memory provider** (backend) as design choices; lifecycle: generate → store → retrieve →
integrate → update → forget. Its types mapped to LangGraph:

| Bootcamp type | LangGraph primitive | Ready option |
|---|---|---|
| working memory | state + checkpointer | built in |
| semantic cache | LLM cache | `RedisSemanticCache`; **not for plans** |
| conversations, summaries | checkpointer, summarisation node | built in, LangMem |
| knowledge base, entity, persona | vector store, Store | RAG stack, Graphiti, LangMem |
| toolbox | Store with embedded tool descriptions | `langgraph-bigtool` (not needed at 4 tools) |
| workflow | checkpoint history distilled into the Store | nothing ready; MemoRizz has the pattern |
| skills | SKILL.md on the Store | deepagents |
| shared / coordination | parent-graph state | built in |

**MemoRizz** (the fork, current with 0.17.16) is the fullest open implementation of that map,
but it is **PolyForm Noncommercial 1.0.0**, runs its own `MemAgent`, and never mentions LangGraph.
Patterns worth reimplementing:

- **Scope on every call** (`agent_id`, `memory_id`, `user_id`, `thread_id`), filters **before**
  the vector top-k, and a tenant-isolation test.
- **Workflow → skill promotion:** a canonical signature (ordered tool names, argument-key shape,
  error class; retries collapsed; values dropped; sha256); **gates** of 5 runs, 80% business
  success, 2 distinct queries; a business-defined outcome evaluator; LLM-distilled SKILL.md;
  **shadow** evaluation; explicit activation; trust levels; **demotion** on drift.
- **Forgetting without deleting:** recency × importance × relevance scoring; reversible
  `retention_state`.
- **Storage is not context:** retrieve → scope → de-duplicate → bound → stable prompt prefix.

How it builds on LangGraph, node vs tool:

| Kind | Node (automatic) | Tool (model-invoked) | Writes |
|---|---|---|---|
| Semantic facts | `recall` top-k | `search_memory`, `save_fact`, `forget` | hot path + background |
| Episodic | `recall_cases` 1–3 | `search_past_cases` | code at outcomes |
| Toolbox | `select_tools` | `find_tools` | at registration |
| Skills | catalog in prompt | `load_skill`, `read_skill_file` | promotion only |
| Workflow | `record_workflow` | — | code, every run |

## 8. Review: a pasted "memory options, Options A–D" analysis

The analysis proposed the Store as ledger, LangMem/MemoRizz-style jobs around it, toolbox memory
as guidance only, and Option A (native episodes) first. **Agreed**, with corrections:

1. **The license is the bigger blocker** than "experimental": MemoRizz code can't go into anything
   commercial, even hardened.
2. It skipped MemoRizz's **mechanics** (canonical signature, gates, shadow/activate/demote,
   business success, scope before top-k), which are what make "never promote automatically" workable.
3. **Toolbox risk is overstated here:** tool retrieval only picks from a developer-written registry.
   The real risks are registering tools you wouldn't want called and retrieval hiding a precheck.
   With 4 tools, bind all of them. "Common failure" notes should be **counts computed from
   traces**, not sentences someone typed.
4. Traces need a **policy version**, or a pre-change failure later reads as current advice.

## 9. Google ADK, and a review of a pasted ADK analysis

> "can we check ADK how it stores episodes and other memory concepts"

Read in the `google-adk` 2.13.0 source:

- **No episode concept.** `MemoryService` stores **session events**, scoped `(app_name, user_id)`.
  Open-source backends: in-memory (keyword overlap, "prototyping only") and SQLite (one row per
  event, `UNIQUE(app, user, session, event)`, FTS5). Only the managed **Vertex AI Memory Bank**
  extracts and consolidates memories with an LLM.
- **State scopes:** `temp:` (this invocation), none (session), `user:`, `app:`.
- **Writes are explicit:** `add_session_to_memory`, `add_events_to_memory` (only new events),
  `add_memory`; `delete_memory`, with deleted ids remembered so a re-ingest can't restore them.
- **Two read tools:** `PreloadMemoryTool` (every LLM request) and `load_memory` (model-invoked),
  the same split as ours.
- **Skills:** `SkillToolset` with PERSISTENT / BOUNDED / EPHEMERAL lifecycles; no learned rules,
  prompts improve offline (GEPA).

Borrow: the scope vocabulary, idempotent incremental writes, remembered deletions, skill unloading.

The pasted ADK analysis was accurate about ADK. Corrections:

1. **`runtime.config[...]` doesn't exist.** `Runtime` has `context, store, stream_writer,
   heartbeat, previous, execution_info, server_info, control`. Use `get_config()` or, better, a
   typed `context_schema` set by the server.
2. **Its namespace made episodes per user** (`("episodes", T, U, ...)`), so one person's
   rejection teaches nobody else. Chosen: shared per tenant with `actor_id` in the value.
3. It missed ADK's **idempotent writes** and **remembered deletions**.

Added from it: a **write gate** (only `Episode`, `Preference`, `WorkflowTrace`, `SkillDraft`
schemas accepted) and provenance fields.

## 10. Review: a pasted namespace model (tenant, user, agent learning)

The model (namespaces for isolation, layers for precedence, learning tenant-scoped) was right.
Four fixes:

1. **Tenant constraints belong in `policy.py`**, as a typed `("policy", T)` config, not in
   procedure text the LLM may ignore. Split tenant rules into *policy* (must hold, code refuses)
   and *procedure* (how to work, prompt advice).
2. **Version in the key, not the namespace;** `planner:active` pointer, so activation and rollback
   are one `put` each.
3. **One third element:** `agent_id` everywhere, not sometimes `"provisioning"`.
4. **Platform procedures stay in git:** a runtime-writable platform namespace would bypass the
   engineering review that is supposed to guard it.

Plus: tenant-shared episodes expose colleagues' request text, so store structured fields, not
free text. This added **step 0** to the build plan (typed tenant policy). Result: the namespace
table in MEMORY.md §4.

## 11. Into the repo

> "can we capture the discussion and be part of the repo docs for this project" · "you had html file created can we store that also in this repo" · "commit and push"

`docs/MEMORY.md` (the design) and `chat_memory_skills/docs/slides.html` (a standalone 19-slide
lesson with notes, exported from the Slides artifact) were committed as `a93d7c2`.

## 12. Review: a pasted two-pipeline capture/learning plan

The plan: a **synchronous** path for trusted facts and recall, an **asynchronous** path for LLM
enrichment and promotion, with a "captured when / used when" table and staged facts. It matched
MEMORY.md almost point for point. Changes:

1. **The tool trace must not go into graph state as-is:** state streams to the browser
   (STATE_SNAPSHOT). Keep it private, or rebuild it at the terminal node from checkpointed messages.
2. **Idempotency from the outcome, not the checkpoint:** a crash between the write and the next
   checkpoint resumes with a new checkpoint id → a duplicate.
3. **No outbox table:** a Store put and an outbox insert aren't one transaction. The episode
   carries `enrichment: "pending"`; the worker scans with a filter.
4. **User facts confirmed by the user** (e.g. a card in the chat); tenant facts by an admin.
5. Smaller: `agent_id` in both namespaces; **`expired`** is its own outcome; **shadow evaluation**
   needs an evaluator: replay the draft on recent recorded requests and compare with what policy
   approved, once when the draft is created.

Adopted from it: `("fact_drafts", T, U)`, the "what enters the LLM context" table (live inventory,
cost and quota are fetched, never recalled), and its closing rule. All three are now in MEMORY.md §5.

## 13. The implementation plan: memory.py first, Postgres from day one

> "Start with memory.py plus tests, then wire it into the graph. But update the blueprint to use Postgres from day one, since that is now the chosen development/production backend."

Four adjustments, all built:

1. **Recall once per new user request** (`START → recall_cases → agent`), not on every return to
   the agent; otherwise tool loops re-run retrieval and re-inject the same cases.
2. **One record per planning attempt** (`attempt_id`): a thread can hold over-budget → policy
   failure → done, and the failed attempts are evidence.
3. **Episode and workflow trace separate;** the trace hashes the **topology** (resource kind,
   dependency shape, property-key shape), not only the top-level `propose_plan` argument keys.
4. **AsyncPostgresSaver + AsyncPostgresStore.**

Boundary: `memory.py` holds schemas, namespace helpers, `recall_cases`, `record_outcome`, the
signature and the renderer, and **no LLM calls, no A2UI, no approval logic**. Index fields:
episodes → `summary`, workflows → `query` (later: facts → `text`, skills → not indexed). Tests
were specified before wiring: tenant isolation, one record per outcome, topology differs when the
architecture does, no names/CIDRs/secrets/raw args, failed and rejected attempts saved, `done` →
success, recall capped at 3, policy/inventory/cost always live.

## 14. Findings while building it

| Finding | Consequence |
|---|---|
| ag-ui-langgraph 0.0.47 builds the run's `context` from `config["configurable"]` (the server's `LangGraphAgent(config=...)` plus `thread_id`) | `server.py` sets `tenant_id` / `user_id` / `agent_id` there; `RequestContext` is Pydantic with `extra="ignore"` so the added `thread_id` and other keys don't break it |
| The adapter does `stream_input = {**forwarded_props, **payload_input}` | **security gap**: any `forwardedProps` key named like a state key (`outcome`, `memoryContext`, `plan`, `messages`) wrote graph input. `trusted()` now drops them (D16) |
| `output_schema=PublicState` keeps private keys out of STATE_SNAPSHOT | `memory_context` and `outcome` are private keys, next to `ag-ui` |
| Sync calls on `AsyncPostgresStore` are routed to its event loop from worker threads | the memory nodes stay sync and work in both the async server and the sync CLI |
| The run's context is not checkpointed | `cli.turn()` passes it on every stream, resumes included |
| A resume continues at the paused node, not START | recall really is once per request, approval pauses included (tested) |
| The graph's terminal phases didn't distinguish expiry, parse failure or a plan that changed during approval | a private `outcome = {kind, reason}` set by the node that ended the attempt: `invalid`, `policy_failed`, `over_budget`, `rejected`, `expired`, `policy_changed`, `done`, `failed` |
| `ValidationError` text and apply errors can contain names, CIDRs, regions | records keep classes only: policy messages → `public_database` etc.; apply errors → their leading identifier (`InsufficientCapacity`) |
| Port 5432 is another project's Postgres; 5433 is a system Postgres without pgvector | the project runs its own `pgvector/pgvector:pg17` on 127.0.0.1:5434, plus `provisioner_test` for tests |
| `inventory.db` is the provider's state file | stays SQLite; it is not agent memory |

Verified: 25 tests (unit, graph with a scripted model on Postgres, server trust), and a smoke run
of the real server with real embeddings: a forged `outcome: done` prop was ignored, the real
`policy_failed` attempt was recorded (1536-dim vectors), and a new thread recalled it.

## 15. Review: a pasted end-to-end walkthrough (first request, second request, procedures)

The walkthrough (checkpoints keep the current job alive, episodes remember past jobs, procedures
encode reviewed lessons) was right in outline. Run against the built code, it differed in seven
places:

1. **A recalled case never shows a cost.** "Final cost was $85/month" is what the renderer leaves
   out on purpose: prices come only from the live estimate. `cost_usd` is stored, not shown.
   Episodes hold resource shapes, not "Acme requested…" or names.
2. **"Require owner tags" is a constraint**, so it belongs in tenant policy `("policy", T)`
   enforced by `policy.py`, not a learned procedure (D7). Quota is already checked by policy.
3. **Lessons from failures need their own path.** The promotion gates count *successes*; "check
   quota before RDS" comes from repeated failures, i.e. counting episodes by issue or error class.
4. **The shadow step was missing** between draft and admin activation.
5. **The trace is not the node list.** Node order and create order are the same every run; the
   trace keeps what varies: LLM tool calls, the topology hash, retries, error classes. "Succeeded
   12 times" is computed by grouping on signature, not stored.
6. **More outcomes** than rejected / over budget / failed / done: also `policy_failed`, `invalid`,
   `expired`, `policy_changed`; an episode **and** a trace for each.
7. Namespace third element is `agent_id` (`"provisioner"`); one record per **attempt**, not per
   thread. Also: only episodes are recalled today; procedures and preferences aren't built.

What the code produces for "staging web app with a database", outcome `done`:

```
Episode:  create staging in us-east-1: rds_instance db.t3.micro postgres, ec2_instance t3.micro,
          security_group, 2 subnet, vpc. Outcome: done.            (cost_usd 22.3, stored)
Trace:    tool_sequence ['propose_plan'], retries 1, success True, topology hash
Recall:   Similar past proposals in this team (ADVICE ONLY: ...):
          - 2026-10-28 · create staging in us-east-1: rds_instance ..., vpc · done
```

## 16. Where working / session memory is stored

> "walk me thro' where do we store session or working memory and how it is stored in postgress store"

Not in the Store: in the checkpointer's tables in the same database. Inspected on a real smoke
thread paused at approval (13 checkpoints): `checkpoints` (the step chain, small values inline),
`checkpoint_blobs` (msgpack values per key and version; `messages` stored whole on every change),
`checkpoint_writes` (per-step node outputs; the pause is one `__interrupt__` row). Read back with
`saver.get_tuple()`, it is the live state again: messages, plan, cost, pending interrupt. The Store
holds the JSON episodes and traces plus their vectors; nothing in the database links the two
sides except the `thread_id` / `attempt_id` copied into a record. Checkpoints are never deleted
today. Details: [MEMORY.md §11](MEMORY.md#11-where-each-layer-lives-in-postgres).

## 17. Hierarchical layers: turn → session → long-term

> "Working memory (turn) → session memory (conversation) → long-term store (cross-session). can we go over where each is stored in postgres db as different dbs or tables how does it work."

One database, not one per layer. Turn and session share the checkpoint tables: a turn is the
stretch of checkpoints that starts at a `source: "input"` checkpoint (shown on a two-turn test
thread: propose → reject, then a second request). Only the assembled prompt is truly per call
and never stored. Per-turn state keys persist with the session until overwritten, which showed
a gap: `phase` stays `rejected` into the next request. Long-term is the Store tables. Session and
Store tables differ in write rate, growth and retention, so they *can* move to two databases
later by giving `persistence.py` two URLs; no graph code changes (D17).

## 18. Review: a pasted "one database, three table families" layout

The layout (one database per environment; LangGraph's checkpoint and Store tables; use the APIs,
not SQL, on them) was right. It proposed three application tables; reviewed:

- **`memory_jobs`** reintroduces the outbox from §12: the Store has its own connection, so a put
  and a job insert can't share a transaction even in one database. The `enrichment` state on the
  episode does the same in one write. Add a jobs table only for leases, retries or priorities.
- **`procedure_reviews`** mostly repeats the immutable `planner:vN` keys (`approved_by`,
  `approved_at`, `source`) and the `:active` pointer; worth it only for rejected drafts, comments
  and shadow results.
- **`audit_events`**: yes, append-only, outside the Store.
- **Missing: checkpoints have no tenant isolation.** They are keyed by `thread_id` alone, so the
  table actually needed is `threads(thread_id, tenant_id, user_id, …)`, checked by `trusted()`.
  It is also what makes retention and user deletion possible (checkpoints can't be searched by
  user); a deletion then covers threads (`delete_thread`) **and** long-term records.

## 19. Review: a pasted Postgres walkthrough of chat_memory_skills' three layers

Checked against `langgraph-checkpoint-postgres` 3.2.0 and chat_memory_skills. Accurate: the two
table families, the turn trace (`recalled`, `save_memory`), `/new` not wiping old threads, and
`store.setup()` running `CREATE EXTENSION vector`. Corrected:

1. **Search is a prefix match** (`= p OR LIKE 'p.%'`), not `prefix = p`.
2. **"Filtered before cosine distance" is not guaranteed.** Verified with `EXPLAIN`: for a
   selective prefix, Postgres uses the prefix B-tree and sorts exactly (safe); when the plan walks
   the HNSW index instead, it filters afterwards, and a forced run gave a small tenant **0 of 3**
   cases. Fixed with `hnsw.iterative_scan = relaxed_order` on Store connections (**3 of 3**),
   tested in `tests/test_vector_scope.py` (D19).
3. **The retention cron can't work:** `checkpoints` has no timestamp column, a delete there
   orphans blobs and writes, and it is SQL on library-owned tables. Use `delete_thread` /
   `prune(strategy="keep_latest")`, and the Store's TTL.
4. **The shared-pool snippet fails:** the pool needs `prepare_threshold=0` and
   `row_factory=dict_row` as well as `autocommit=True`.
5. Smaller: working vs session memory aren't different tables (every key is a channel in the same
   three); chat_memory_skills has no summarisation yet; separate schemas need one pool per
   `search_path`; a global `index.fields` list embeds whichever of those fields a record has,
   while cloud_provisioner names them per `put`.

## Still open

- `search_past_cases` tool, lesson lines (background, durable via `enrichment` state), merge of
  near-duplicates, `policy_version` on records, `retention_state` and user deletion.
- Step 0: typed tenant policy `("policy", T)` read by `policy.py`.
- Preferences and facts (`("preferences", T, U)`, `("fact_drafts", T, U)` → `("facts", T, U)`).
- Promotion: gates → `skill_drafts` → shadow → admin activation → `:active` → demotion.
- Auth: real tenant and user ids, thread ownership, who may approve. Until then, fixed dev ids.
- Housekeeping: reset per-attempt keys such as `phase` at the start of each request; a retention
  job (`prune(strategy="keep_latest")` for idle threads, `delete_thread` for expired ones) driven by
  a `threads` table, which is also the thread-ownership check.
- An end-to-end example section in MEMORY.md built from the real records in §15.
