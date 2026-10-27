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
The right-hand panel logs every event, so you can watch the protocol as it happens. `server.py` allows CORS from
`localhost:5173` for this. Both clients drive the same server: AG-UI is the contract, and the UI is up to you.

| | `web/` (CopilotKit) | `web_plain/` |
|---|---|---|
| path | browser → Next.js runtime → AG-UI → FastAPI | browser → AG-UI → FastAPI |
| chat, streaming, tool cards | CopilotKit components | about 300 lines of plain JS |
| approval | `useInterrupt` → `resolve()` | `RUN_FINISHED.outcome` → button → POST with `resume[]` |
| a server in front of the agent (auth, secrets) | the Next.js runtime | none: the agent must be reachable from the browser |

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
