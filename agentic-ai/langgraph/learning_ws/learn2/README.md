# learn2 — state machines, built with FastAPI

LangGraph's `StateGraph` looks like new machinery, but it's the same shape
as a web app: named handlers (**nodes**), a routing table between them
(**edges**), and a value that gets passed along and updated at each stop
(**state**). Both samples below build that shape with nothing but FastAPI,
to make the analogy concrete. The tiny engine they share —
`src/learn2/mini_graph.py` — is deliberately small enough to read in one
sitting; every sample module only has to show its own nodes and edges.

| LangGraph                            | `learn2.mini_graph`                              |
| ------------------------------------- | ------------------------------------------------- |
| `state: TypedDict`                    | `state: SomeModel(BaseModel)`                      |
| `graph.add_node(name, fn)`            | `graph.add_node(name, fn)` / `@node("name")`       |
| `fn(state) -> dict` (partial update)  | same contract, unchanged                           |
| `graph.add_edge(a, b)`                | `graph.add_edge(a, b)`                             |
| `graph.add_conditional_edges(a, fn)`  | `graph.add_edge(a, fn)` where `fn(state) -> name`  |
| `START` / `END`                       | `START` / `END`                                    |
| `graph.compile().invoke(state)`       | `graph.invoke(state)`                              |

Each node is registered on the graph *and* exposed as its own FastAPI route
(`POST /nodes/{name}`), so you can call one node in isolation — the same
way you'd unit-test a single LangGraph node function without running the
whole graph. `POST /graph/run` walks the whole routing table end to end and
returns the path it took (`trace`) plus the final state — that loop is
literally what `CompiledGraph.invoke()` does internally.

## Sample 1 — order processing (`src/learn2/state_machine/app.py`)

```
START -> receive_order -> validate_order -+-> fulfill_order -+-> notify_customer -> END
                                           +-> reject_order  -+
```

`validate_order` branches based on the state — that's a conditional edge.

```bash
uv run uvicorn learn2.state_machine.app:app --reload --port 8000
```

```bash
# run the whole graph
curl -s -X POST http://127.0.0.1:8000/graph/run \
  -H 'content-type: application/json' \
  -d '{"order_id": "A1", "amount": 42.0, "stock_available": true}' | jq

# take the reject branch
curl -s -X POST http://127.0.0.1:8000/graph/run \
  -H 'content-type: application/json' \
  -d '{"order_id": "A2", "amount": 42.0, "stock_available": false}' | jq

# call one node in isolation, like unit-testing a LangGraph node
curl -s -X POST http://127.0.0.1:8000/nodes/validate_order \
  -H 'content-type: application/json' \
  -d '{"order_id": "A3", "amount": 10.0, "stock_available": true}' | jq
```

## Sample 2 — controller → service → formatter (`src/learn2/api_pipeline/app.py`)

The classic web-app layering is exactly a small graph: a **controller**
that accepts and normalizes the request, a **service** that is the only
node allowed to talk to the network (it calls the public GitHub API), and
a **formatter** that shapes the response for the caller. If the API call
fails, a conditional edge routes to an error-formatting node instead.

```
START -> controller -> service -+-> formatter     -> END
                                 +-> format_error  -> END
```

This exact flow is also implemented directly with LangGraph's `StateGraph`
in `../learn1/src/learn1/my_sample1/example2.py` — open the two files side
by side; every `add_node` / `add_edge` / `add_conditional_edges` call in
the LangGraph version has a literal counterpart here. And
`../learn1/src/learn1/my_sample1/example3.py` builds the *same* flow with
no framework at all — the same node functions, wired with plain
sequential calls and an `if/else` — to show the graph shape isn't special
machinery.

```bash
uv run uvicorn learn2.api_pipeline.app:app --reload --port 8001
```

```bash
# success path — hits a real GitHub profile
curl -s -X POST http://127.0.0.1:8001/graph/run \
  -H 'content-type: application/json' \
  -d '{"username": "octocat"}' | jq

# failure path — takes the format_error branch
curl -s -X POST http://127.0.0.1:8001/graph/run \
  -H 'content-type: application/json' \
  -d '{"username": "this-user-should-not-exist-12345"}' | jq

# call the controller node in isolation
curl -s -X POST http://127.0.0.1:8001/nodes/controller \
  -H 'content-type: application/json' \
  -d '{"username": "  OctoCat  "}' | jq
```

Swagger UI for either app is at `http://127.0.0.1:<port>/docs`.
