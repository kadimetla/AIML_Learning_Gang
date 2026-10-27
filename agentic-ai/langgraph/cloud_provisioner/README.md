# cloud_provisioner

A LangGraph agent that provisions AWS-style infrastructure from a chat:
**plan → policy check → cost estimate → human approval → apply → report**.
It runs in the terminal, and in a CopilotKit web UI over the AG-UI protocol. Both
use the same graph.

The LLM only *proposes* (a `propose_plan` tool call with a structured plan).
Plain code validates and prices it, a human approves it (`interrupt()`), and only then
does the provider touch the cloud. By default that cloud is a **fake** one: no
credentials and no cost. A real **AWS** provider (boto3) uses the same interface
for when you test for real.

Step-by-step walkthrough for students: **[docs/FLOW.md](docs/FLOW.md)** (the graph) and **[docs/ORCHESTRATION.md](docs/ORCHESTRATION.md)** (the request across all services)

```
START → agent ⇄ tools                     list_catalog, list_resources
          │ propose_plan / propose_destroy
          ▼
        plan → validate → estimate → approve ──→ apply ⟲ (one resource per step) → report
                  │          │          │                                           │
                  └──────────┴──────────┴─ problems / rejected ─────────────────────┴──→ agent
```

| File | What it is |
|---|---|
| `graph.py` | the workflow: state, tools, nodes, edges |
| `catalog.py` | `Plan` / `Resource` models (AWS kinds), prices, `estimate()`, dependency order |
| `policy.py` | guardrails in plain code: regions, names, open SSH, public DB, 2 AZs, quota, budget, no prod destroy |
| `cloud.py` | `Inventory` (our "state file", `inventory.db`), `FakeCloud`, `get_provider()` |
| `aws_cloud.py` | `AwsCloud`: the same `create` / `delete` with boto3 |
| `cli.py` | terminal chat; approval is a y/N prompt |
| `demo.py` | scripted run: policy fix → reject → approve + retry → destroy |
| `server.py` | AG-UI endpoint (`ag-ui-langgraph`) + `GET /inventory` |
| `web/` | Next.js + CopilotKit: chat, plan panel (`useAgent`), approve card (`useInterrupt`), inventory |
| `web_plain/index.html` | the same UI in one file with no libraries: `fetch` + SSE straight to the AG-UI server, plus a raw event log |
| `web_hybrid/` | Vite + React: `@ag-ui/client` runs the agent, CopilotKit's `CopilotChatView` draws the chat; no runtime |
| `a2ui.py` | A2UI on the server: the code-built `ask_details` form, the switch (did the client send a catalog?) |
| `web_shadcn/` | Vite + shadcn/ui, no CopilotKit: a headless AG-UI hook, a shadcn chat, and an A2UI renderer whose catalog maps A2UI types to shadcn components |
| `web_assistant_ui/` | the same, with assistant-ui's AG-UI runtime and chat primitives in place of the hook and chat |

## Run (fake cloud)

```bash
cp .env.example .env          # set OPENAI_API_KEY
uv sync
uv run demo.py                # scripted, about 1 minute
uv run cli.py                 # chat yourself: /inventory /new /quit
```

Web UI, in two terminals:

```bash
uv run server.py                          # AG-UI on http://127.0.0.1:8001/agent
cd web && npm install && npm run dev      # http://localhost:3001
```

Ports 8001 and 3001 let this run next to `chat_memory_skills` (8000 / 3000).

### Plain AG-UI client (no CopilotKit, no Next.js)

```bash
uv run server.py                                  # same agent server
python3 -m http.server 5173 -d web_plain          # http://localhost:5173
```

One HTML file speaks AG-UI directly: it POSTs a `RunAgentInput` to `:8001/agent` and reads the SSE events.
The right-hand panel logs every event, so you can watch the protocol as it happens.

### Hybrid client (CopilotKit components, your own AG-UI loop, no runtime)

```bash
uv run server.py                                  # same agent server
cd web_hybrid && npm install && npm run dev       # http://localhost:5174
```

`@ag-ui/client`'s `HttpAgent` sends the runs (including `resume[]` for approvals) and keeps the messages and
state. `CopilotChatView` only draws them. The page calls `/agent` and `/inventory` on its **own origin**, and a
proxy routes them to FastAPI: Vite's dev server (`vite.config.ts`) in development, nginx in production
(`web_hybrid/deploy/nginx.conf`, an untested example with SSE settings: `proxy_buffering off`, long read timeout).
So there's no CORS, and FastAPI never has to face the internet. `CopilotKitProvider` is still needed, because the message view reads
its tool renderers from it. The agent is passed in as a local agent (`agents__unsafe_dev_only`), so the
provider never looks for a runtime.

### shadcn + A2UI client (no CopilotKit)

```bash
uv run server.py                                  # same agent server
cd web_shadcn && npm install && npm run dev       # http://localhost:5175 (same proxy setup as web_hybrid)
```

[A2UI](https://a2ui.org) lets the agent describe UI as JSON (a flat list of components plus a data model). The
client draws it with its **own** components. Here, the client's catalog (`src/a2ui/catalog.tsx`) maps each A2UI type
to a shadcn component: `ChoicePicker` → `Select`, `TextField` → `Input`/`Textarea`, `Card` → `Card`, `Button` → `Button`, and so on.

```
useAgUi (agui/)        AG-UI run loop; sends the catalog's schema in RunAgentInput.context on every run
ChatView (chat/)       shadcn chat, presentational; a renderTool slot and a footer slot
A2UISurface (a2ui/)    A2UI ops -> catalog[type] -> shadcn; unknown types render as "unsupported"
```

| A2UI in this app | made by | arrives as | the answer goes back as |
|---|---|---|---|
| `ask_details` form (env, region, budget, needs) | **code** (`a2ui.details_form`); the LLM only prefills it | `interrupt()` value, `reason: "a2ui:form"` | the button's A2UI action as the `resume[]` payload |
| views ("show staging as cards") | an **LLM sub-agent** (`generate_a2ui` from `ag-ui-langgraph`), validated and retried by its toolkit | tool result `{"a2ui_operations": [...]}` | a button click becomes a user message |
| approval card | **not A2UI**: hand-built from validated, priced state | `interrupt()` value, `reason: "plan:approval"` | `resume[]` with `{approved}` |

The A2UI tools are offered only when the request carries an A2UI catalog. `web/`, `web_plain/`, `web_hybrid/` and
`cli.py` don't send one, so they never see a form interrupt. A view made by an LLM can be wrong (in a test run, its
cards showed rounded costs), which is why the thing a human approves is never LLM-made UI. If small models
produce invalid views, set `A2UI_MODEL` to a stronger model just for designing them.

### assistant-ui + A2UI client

```bash
uv run server.py                                  # same agent server
cd web_assistant_ui && npm install && npm run dev # http://localhost:5176 (same proxy setup)
```

The same app as `web_shadcn`, but [assistant-ui](https://www.assistant-ui.com)'s AG-UI runtime replaces our
`useAgUi` hook and `ChatView`. The A2UI renderer, catalog and panels are copies of `web_shadcn`'s, and the server is unchanged.

```
ProvisionRuntime (agui/runtime.tsx)  HttpAgent + useAgUiRuntime; the A2UI catalog via getRunContext;
                                     the only file that imports @assistant-ui/react-ag-ui
Thread (chat/)                       assistant-ui primitives with a shadcn look; tool parts drawn by name
A2UISurface (a2ui/)                  unchanged: A2UI ops -> catalog -> shadcn
```

- **Pauses:** `useAgUiInterrupts` / `useAgUiSubmitInterruptResponses`, wrapped in `usePendingInterrupt()`, which refuses
  to answer half of several open interrupts (the runtime requires an answer for each).
- **`joinStrategy: "concat-content"` is required.** One graph run is several LLM turns, so the run's closing
  `MESSAGES_SNAPSHOT` has several assistant messages. Without joining, the last one shows the open `propose_plan`
  call as a pending *browser* tool, the interrupt isn't seen as pending, and no approval card appears.
- **assistant-ui's own A2UI support is not used.** It expects surfaces as `ACTIVITY_SNAPSHOT` events and sends clicks as
  `forwardedProps.a2uiAction`; `ag-ui-langgraph` and our graph use tool results and `interrupt()` instead.
- **No retry / edit buttons yet.** Both send a shorter transcript, and `ag-ui-langgraph` then forks the thread from an
  earlier checkpoint. Test that around a pause before adding them.
- `@assistant-ui/react-ag-ui` 0.1.0 and `@ag-ui/client` 1.0.3 were under two weeks old when pinned (0.1.0 is the first
  version on `@ag-ui/client` 1.x). The interrupt hooks are new; expect API changes, and keep them inside `runtime.tsx`.

### What the server does not take from the browser

The browser is untrusted. These hold for every client:

- **Graph state comes from the checkpoint.** The `state` a client sends is replaced with the thread's own, and
  `forwardedProps.nodeName` / `command` are dropped. Without this, one request could write a plan "as `approve`"
  and go straight to `apply`, skipping policy, pricing and the human.
- **An answer must match the open pause.** A `resume` whose `interruptId` isn't open on the thread gets HTTP 409,
  so a stale or replayed Approve can't approve a newer plan.
- **An approval is checked again.** It expires (`APPROVAL_TTL_MIN`, default 30), and after the "yes" the plan is
  re-checked against the *current* inventory before anything is created.
- **Form answers are typed.** `ask_details` values pass a Pydantic model (known env/region, budget bounds, no
  extra fields) before the LLM sees them.

Not done yet: authentication, thread ownership (any caller who knows a thread id can use it), and who may approve.

### Five clients, one agent server

`server.py` allows CORS only from `localhost:5173`, for `web_plain`, which calls it directly from the browser. All five drive the same server: AG-UI is the contract, and the UI is up to you.

| | `web/` | `web_hybrid/` | `web_shadcn/` | `web_assistant_ui/` | `web_plain/` |
|---|---|---|---|---|---|
| path | browser → Next.js runtime → AG-UI → FastAPI | browser → proxy → AG-UI → FastAPI | same as hybrid | same as hybrid | browser → AG-UI → FastAPI |
| runs the agent | CopilotKit (through the runtime) | `@ag-ui/client` `HttpAgent` | `HttpAgent` inside `useAgUi` | `HttpAgent` inside `useAgUiRuntime` | your own `fetch` + SSE loop |
| draws the chat | `CopilotChat` | `CopilotChatView` (display only) | your shadcn `ChatView` | assistant-ui primitives, shadcn look | about 300 lines of plain JS |
| approval | `useInterrupt` → `resolve()` | `RUN_FINISHED.outcome` → card → `runAgent({ resume })` | same as hybrid | `useAgUiInterrupts` → card → `useAgUiSubmitInterruptResponses` | same, by hand |
| generative UI | — | — | A2UI → shadcn catalog | same renderer as web_shadcn | — |
| build step | Next.js | Vite | Vite + Tailwind | Vite + Tailwind | none |
| server in front of the agent (auth, secrets) | yes, the runtime | the proxy (Vite dev / nginx) | the proxy | the proxy | none |
| supported by CopilotKit | yes | uses a dev-only prop; pin the version | doesn't use CopilotKit | doesn't use CopilotKit | doesn't use CopilotKit |

## Real AWS

```bash
uv sync --extra aws
CLOUD_PROVIDER=aws uv run cli.py          # uses your normal AWS profile / credentials
```

- **Try LocalStack first** (a local AWS emulator). boto3 reads the endpoint from the environment, so no code changes:
  `AWS_ENDPOINT_URL=http://localhost:4566 AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test CLOUD_PROVIDER=aws uv run cli.py`
  If the emulator has no SSM AMI parameter, set `AWS_AMI_ID`.
- Use a **sandbox account** with a billing alarm, and IAM permissions for EC2, RDS, S3 and SSM read only.
- Everything created is tagged `Project=cloud-provisioner`, `Env`, `Name`. The DB password is generated and kept by
  Secrets Manager (`ManageMasterUserPassword`), so no secret ever passes through the LLM.
- RDS takes about 5–10 minutes to create and delete. **Destroy the env when you are done.** Real resources cost real money.
- `inventory.db` is the only record of what was created (like a Terraform state file). Don't delete it while resources exist.
- `aws_cloud.py` has not yet been run against real AWS. Expect to fix small things on the first real run.

## Exercises

1. Add a `load_balancer` kind (ALB): catalog price, a policy rule (needs 2 public subnets), and the fake + AWS create/delete.
2. Only an "ops" user may approve `prod`. Pass the user from `server.py` and check it in `approve`.
3. Add a `drift` tool: compare `inventory.db` with what the provider reports.
4. Replace `apply` with `terraform plan` / `terraform apply` on generated HCL. The graph stays the same.
