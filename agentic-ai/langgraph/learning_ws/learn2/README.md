# learn2 — a state machine, built with FastAPI

LangGraph's `StateGraph` looks like new machinery, but it's the same shape
as a web app: named handlers (**nodes**), a routing table between them
(**edges**), and a value that gets passed along and updated at each stop
(**state**). This sample builds that shape with nothing but FastAPI to make
the analogy concrete.

The example is a small order-processing pipeline:

```
START -> receive_order -> validate_order -+-> fulfill_order -+-> notify_customer -> END
                                           +-> reject_order  -+
```

`validate_order` branches based on the state — that's a conditional edge.

## The mapping

| LangGraph                             | `src/learn2/state_machine/app.py`               |
| -------------------------------------- | ------------------------------------------------ |
| `state: TypedDict`                     | `OrderState(BaseModel)`                          |
| `graph.add_node(name, fn)`             | `@node("name")` decorator on a plain function     |
| `fn(state) -> dict` (partial update)   | same contract, unchanged                          |
| `graph.add_edge(a, b)`                 | `edge(a, b)`                                      |
| `graph.add_conditional_edges(a, fn)`   | `edge(a, fn)` where `fn(state) -> next_node_name` |
| `START` / `END`                        | `START` / `END`                                   |
| `graph.compile().invoke(state)`        | `run_graph(state)`                                |

Each node is registered in a plain dict (`NODES`) *and* exposed as its own
FastAPI route (`POST /nodes/{name}`), so you can call one node in isolation
— the same way you'd unit-test a single LangGraph node function without
running the whole graph. `POST /graph/run` walks the whole routing table
end to end and returns the path it took (`trace`) plus the final state —
that loop is literally what `CompiledGraph.invoke()` does internally.

## Run it

```bash
uv run uvicorn learn2.state_machine.app:app --reload
```

Then open http://127.0.0.1:8000/docs for interactive Swagger UI, or:

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
