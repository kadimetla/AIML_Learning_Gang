# Worked solutions for the slide-deck exercises

Each solution was run against this repo (`gpt-4o-mini`, `temperature=0`) and then
reverted. Run commands from `sample5/`. Add `--show-llm` to any script to watch
what the model is sent.

---

## Exercise 1 -- add a `subtract` tool to the math server

**Goal:** show that the agent picks up a new MCP tool with **no client change**.

Edit `servers/math_server.py` and add, next to `add` / `multiply`:

```python
@mcp.tool()
def subtract(a: float, b: float) -> float:
    """Subtract b from a (a - b)."""
    return a - b
```

Run (change the question in `01_stdio.py` to e.g. `"What is 100 minus 58? Use the tools."`):

```bash
uv run 01_stdio.py --show-llm
```

Observed:

```
MCP tools: ['add', 'multiply', 'subtract']
  subtract(a=100, b=58) -> 42.0
100 minus 58 is 42.
```

**Why it works:** `client.get_tools()` runs `tools/list` at startup, so the
client always discovers whatever the server currently offers. With `--show-llm`
you will see `subtract` appear in "tools sent" with the schema FastMCP built from
the type hints, and the **docstring became the tool description the model reads**.

**Discussion:** change the docstring to something vague (`"""does math"""`) and
ask the same question -- tool descriptions are prompt engineering.
Also: the stdio server restarts every run, so there is nothing to redeploy.
With the HTTP server (sample 2) you must restart the server process yourself.

---

## Exercise 2 -- add a `shipping-delay` skill

**Goal:** show skills are discovered from the server's resources, not hard-coded.

Create `skills/shipping-delay/SKILL.md`:

```markdown
---
name: shipping-delay
description: Decide what compensation to offer when an order arrives late. Use when the user complains about a late, delayed or missing delivery.
---

Compensation depends on how many days late the order was:

- 1-3 days late: apologise, no credit.
- 4-7 days late: $10 store credit.
- More than 7 days late: $25 store credit and free expedited reshipping.

If the customer did not say how many days late, ask before offering anything.
```

No code changes: `servers/skills_server.py` walks `skills/` at startup and
registers every file as `skill://shipping-delay/...`. Change a question in
`03_skills.py` to:

```python
await ask(app, "Order A100 arrived 6 days late. What can we offer the customer?")
```

```bash
uv run 03_skills.py --show-llm
```

Observed:

```
discovered skills:
- refund-policy: ...
- shipping-delay: Decide what compensation to offer when an order arrives late. ...
- support-tone: ...
load_skill(name="shipping-delay")
Order A100 arrived 6 days late -> we can offer a $10 store credit.
```

**What to point out in the `--show-llm` trace**
- Request #1's `[system]` message now lists three skills, but only name +
  description -- the bullet rules are **not** in the prompt yet.
- The rules reach the model only in request #2, as the `tool` message returned by
  `load_skill`. That is progressive disclosure.
- The `description` is what makes the model choose the skill. Reword it to
  something unrelated (`"Pirate greetings"`) and the model will stop loading it.

**Note:** this skill needs no MCP tool, only judgement rules. Compare with
`refund-policy`, which tells the model to call `lookup_order`.

---

## Exercise 3 -- break it with a `print()` in the stdio server

**Goal:** see why stdout belongs to the protocol in stdio servers.

Try these in `servers/math_server.py`, each placed right above `mcp = FastMCP("math")`.
Results are what actually happened here (`mcp` 1.30):

| Change | Result |
|---|---|
| `print("debug: starting")` | **Works.** The text is sitting in Python's stdout buffer and never reaches the client before it disconnects. Your debug message is silently lost. |
| `print("debug: starting", flush=True)` | **Works, but noisy.** The client logs `Failed to parse JSONRPC message from server` (5 times in one run) and skips the bad line. |
| `print("debug", end="", flush=True)` | **Breaks.** No newline, so it glues onto the next message: `debug{"jsonrpc":"2.0",...}`. The `initialize` reply cannot be parsed, the handshake never completes, and the script **hangs** until killed (exit 124 under `timeout`). |

**Takeaways**
1. Never write to stdout from a stdio server. The SDK happens to skip whole bad
   lines, but that is an implementation detail -- the same code can hang
   depending on buffering and newlines, which makes it a nasty bug to chase.
2. For debug output use stderr: `print("debug", file=sys.stderr)` or
   `logging` (default handler writes to stderr). The client shows the server's
   stderr in your terminal -- that is where the `Processing request of type ...`
   lines come from.
3. This problem **does not exist with streamable HTTP** (sample 2): the protocol
   travels over the network, so `print()` in `weather_http_server.py` just goes
   to that server's console. Try it.
