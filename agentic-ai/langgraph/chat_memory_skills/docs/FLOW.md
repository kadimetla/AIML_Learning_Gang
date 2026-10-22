# How one chat turn flows through chat_memory_skills

A step-by-step walkthrough for teaching. Each step points at the code that
does it. The traces are real output from `uv run demo.py`.

## 0. The big picture

```
 you type ──► chat.py REPL ──► app.stream(input, config) ──► LangGraph graph
                                                              │
       ┌──────────────────────────────────────────────────────┘
       ▼
 START ──► recall ──► agent ──(tool calls?)──► tools ──┐
                        ▲            │ no              │
                        │            ▼                 │
                        │           END                │
                        └──────────────────────────────┘

 checkpointer (checkpoints.db)  ← saves the thread's state after every step
 store        (memories.db)     ← long-term facts, read by recall, written by tools
```

Sections 1–5 use the terminal client (`chat.py`), which calls the compiled
graph as a Python object in the same process: no server, no protocol. Section 6
runs the **same graph** behind a web UI with AG-UI and CopilotKit.

## 1. Startup (once per process)

| # | What happens | Code |
|---|---|---|
| 1.1 | Skills are discovered: `skills/*/SKILL.md` is scanned and only the frontmatter (`name`, `description`) is kept in `CATALOG`. | `skills.py:24`, `skills.py:33` |
| 1.2 | The two persistence objects are opened: `SqliteSaver` (short-term) and `SqliteStore` with an embedding index on the `fact` field (long-term). | `chat.py:72` |
| 1.3 | The graph is built: 3 nodes, 4 edges. The LLM is bound to all 6 tools so it knows their names and argument schemas. | `chat.py:51-69` |
| 1.4 | The graph is compiled with **both** objects attached: `compile(checkpointer=saver, store=store)`. From then on, LangGraph handles checkpointing, and nodes and tools can reach the store with `get_store()`. | `chat.py:111` |
| 1.5 | A thread id is chosen (random, or `--thread`). The user id comes from `--user`. | `chat.py:113` |

## 2. One turn: the user presses Enter

The REPL builds the **config** and starts a run:

```python
config = {"configurable": {"thread_id": thread, "user_id": args.user}}   # chat.py:137
app.stream({"messages": [("user", text)]}, config, stream_mode="updates")  # chat.py:86
```

- `thread_id` tells the **checkpointer** which conversation this is.
- `user_id` is our own key. `memory.py` reads it with `get_config()` to pick
  the store namespace `("memories", user_id)`.
- The input contains **only the new message**. The history comes from the
  checkpointer, not from the caller.

### Step 2.1: Load short-term memory (automatic)

LangGraph loads the latest checkpoint for `thread_id`. The new user message is
**appended** to `state["messages"]`, not swapped in for them, because
`MessagesState` uses the `add_messages` reducer. On a new thread the list
starts empty.

### Step 2.2: `recall` node reads long-term memory

```python
query = state["messages"][-1].content                          # memory.py:31
hits = get_store().search(namespace(), query=query, limit=5)   # memory.py:32
return {"recalled": [...]}
```

The store embeds the user's message and returns this user's most similar
facts. Only this user's namespace is searched, so other users' memories never
show up.

```
  [recall] [88f3d69a] User is vegetarian.
  [recall] [86aedd03] User is allergic to peanuts.
```

### Step 2.3: `agent` node calls the LLM

`agent_node` (`chat.py:54`) builds the **system prompt fresh every time**:

```
You are a helpful assistant with memory, tools and skills.
Skills (call load_skill BEFORE acting on a matching request ...):
- meal-planner: Suggest meals or a dinner plan. ...        ← catalog only, not the body
- refund-policy: Decide whether a customer order ...
Memory: when the user tells you a durable fact ... call save_memory ...
Known about this user (from earlier conversations):
[88f3d69a] User is vegetarian.                             ← from recall
[86aedd03] User is allergic to peanuts.
```

It sends `[system, *state["messages"]]` to the LLM. The model returns an
`AIMessage` that contains **either** text (the answer) **or** `tool_calls`.

### Step 2.4: Routing with `tools_condition`

`tools_condition` (`chat.py:67`) looks at the last message:
- it has `tool_calls`: go to the `tools` node
- it has none: go to `END`

### Step 2.5: `tools` node runs what the model asked for

`ToolNode` runs every requested call, in parallel when there are several, and
appends one `ToolMessage` per call. Then the `tools → agent` edge
(`chat.py:68`) loops back to step 2.3. The LLM now sees the results.

The loop **2.3 → 2.4 → 2.5 → 2.3** repeats until the model answers with text.

### Step 2.6: END and save (automatic)

The checkpointer has saved state after **every** step. Next turn on the same
`thread_id` continues from here. The REPL prints the last message's content.

## 3. Worked example: "Can I get a refund on order A300?"

This one turn makes **4 LLM calls**:

| Loop | Node | What happens | Why |
|---|---|---|---|
| — | recall | finds the vegetarian and peanut facts | irrelevant here, but recall always runs |
| 1 | agent | → `load_skill("refund-policy")` | the catalog matches "refund", and the prompt says to load a skill first |
| 1 | tools | returns the full `SKILL.md` | **progressive disclosure**, step 2 |
| 2 | agent | → `lookup_order("A300")` | SKILL.md step 1 says to call it |
| 2 | tools | `{"status": "delivered", "total": 900, "age_days": 5}` | ordinary tool = capability |
| 3 | agent | → `read_skill_file("refund-policy", "references/escalation.md")` | SKILL.md step 3: total > $500 |
| 3 | tools | escalation rules | **progressive disclosure**, step 3 (drill) |
| 4 | agent | text: "eligible ... pending manager approval" | no tool calls → END |

After this turn, `state["messages"]` for the thread holds:
`Human, AI(tool_call), Tool, AI(tool_call), Tool, AI(tool_call), Tool, AI(text)`,
plus everything from earlier turns.

## 4. Worked example: the two memory layers

```
thread A  "I'm vegetarian and allergic to peanuts."
            agent → save_memory × 2  (one tools step, run in parallel)
            → store: ("memories","demo") gets 2 items        ← LONG-term WRITE

thread A  "What was the total on that order?"
            no tool calls. The answer ($900) comes from the ToolMessage
            in the thread history                            ← SHORT-term

thread B  "What should I cook for dinner tonight?"
            new thread_id → empty history
            recall → vegetarian, peanuts                     ← LONG-term READ
            agent → load_skill("meal-planner") → 3 vegetarian dishes
```

| Question to ask students | Answer |
|---|---|
| Why does thread B know about the diet? | `recall` searches the store by `user_id`, not `thread_id` |
| Why doesn't thread B know about order A300? | that lives in thread A's messages (checkpointer), keyed by `thread_id` |
| Who decides what is a "memory"? | the LLM, by calling `save_memory`. That's what the system prompt asks for |
| What does `--user sam` see? | nothing: a different namespace |

## 5. Who is responsible for what

| Concern | Done by | We wrote code? |
|---|---|---|
| Keep conversation history | checkpointer + `add_messages` reducer | no, just `compile(checkpointer=...)` |
| Loop until done | `tools_condition` + `tools → agent` edge | 2 lines |
| Run tools, return results | `ToolNode` | no |
| Remember user facts | `save_memory` tool + store | yes, `memory.py` |
| Bring facts back | `recall` node + store vector search | yes, `memory.py` |
| Know-how on demand | skill catalog in prompt + `load_skill` | yes, `skills.py` |

## 6. The web version: CopilotKit UI → AG-UI → the same graph

```
 Browser :3000                Next.js server :3000              Python :8000
┌───────────────────┐       ┌─────────────────────────┐       ┌────────────────────────┐
│ web/app/page.tsx  │ HTTP  │ /api/copilotkit/*       │ AG-UI │ server.py  POST /agent │
│ <CopilotChat>     │──────►│ CopilotRuntime          │──────►│ ag_ui_langgraph        │
│ tool-call cards   │◄──────│ HttpAgent(url=:8000)    │◄─SSE──│ → build_graph() ...    │
└───────────────────┘       └─────────────────────────┘       └────────────────────────┘
       React UI                pure forwarder, no AI            same graph as chat.py
```

| Piece | Role | Code |
|---|---|---|
| **CopilotKit (React)** | the chat window, streaming text, a card per tool call | `web/app/page.tsx` |
| **CopilotRuntime** | backend-for-frontend: the browser never calls Python directly; the runtime forwards to the agent over AG-UI | `web/app/api/copilotkit/[[...slug]]/route.ts` |
| **AG-UI** | the protocol: one HTTP POST in (`RunAgentInput`), a Server-Sent-Events stream of typed events out | (wire format) |
| **ag-ui-langgraph** | adapter: turns `RunAgentInput` into a graph run, and LangGraph's `astream_events` into AG-UI events | `server.py` |
| **the graph** | unchanged: recall → agent ↔ tools, checkpointer, store | `chat.py: build_graph()` |

### 6.1 One web turn, step by step

1. **Browser.** The user types into `<CopilotChat>`. CopilotKit sends the run
   to `/api/copilotkit` with the agent id `default`, the `threadId` (our
   thread id) and `properties` (`{user_id}`).
2. **CopilotRuntime** (`route.ts`) looks up agent `default` = `HttpAgent` and
   POSTs an AG-UI **`RunAgentInput`** to `http://127.0.0.1:8000/agent`:
   ```json
   { "threadId": "0072befd", "runId": "...",
     "messages": [ {"id": "u1", "role": "user", "content": "Refund on A300?"} ],
     "forwardedProps": { "user_id": "demo" }, "state": {}, "tools": [], "context": [] }
   ```
3. **server.py** reads `forwardedProps.user_id` and builds a `LangGraphAgent`
   with `config={"configurable": {"user_id": ...}}`. The adapter adds
   `thread_id = threadId` itself.
4. **Adapter:** loads the thread's checkpoint (`aget_state`), merges in any
   new messages by id, and runs `graph.astream_events(...)`.
5. **Graph:** exactly sections 2.1–2.6: recall → agent → tools → agent → END.
6. **Adapter → AG-UI events**, streamed back as SSE as they happen. Captured
   from a real "refund on A100?" turn (repeats collapsed):
   ```
   RUN_STARTED
   STEP_STARTED recall · STATE_SNAPSHOT · STEP_FINISHED recall
   STEP_STARTED agent  · TOOL_CALL_START load_skill · TOOL_CALL_ARGS ×6 · TOOL_CALL_END
                         STATE_SNAPSHOT · STEP_FINISHED agent
   STEP_STARTED tools  · TOOL_CALL_RESULT · STATE_SNAPSHOT · STEP_FINISHED tools
   STEP_STARTED agent  · TOOL_CALL_START lookup_order · TOOL_CALL_ARGS ×7 · TOOL_CALL_END
                         STATE_SNAPSHOT · STEP_FINISHED agent
   STEP_STARTED tools  · TOOL_CALL_RESULT · STATE_SNAPSHOT · STEP_FINISHED tools
   STEP_STARTED agent  · TEXT_MESSAGE_START · TEXT_MESSAGE_CONTENT ×22 · TEXT_MESSAGE_END
                         STATE_SNAPSHOT · STEP_FINISHED agent
   STATE_SNAPSHOT · MESSAGES_SNAPSHOT
   RUN_FINISHED
   ```
   Each `STEP_*` pair is one graph node; you can read the agent ↔ tools loop
   straight off the stream. `TOOL_CALL_ARGS` and `TEXT_MESSAGE_CONTENT` are
   token-by-token chunks.
7. **CopilotRuntime** relays the stream; **CopilotKit** draws it: each
   `TOOL_CALL_*` becomes a card (via `useDefaultRenderTool`), and
   `TEXT_MESSAGE_CONTENT` chunks are typed out as they arrive.

### 6.2 Terminal vs web, side by side

| Concern | `chat.py` (terminal) | web (AG-UI + CopilotKit) |
|---|---|---|
| user input | `input()` | `<CopilotChat>` |
| thread id | `thread` variable, `/new` | `threadId` prop, "New thread" button |
| user id | `--user` flag | `properties.user_id` → `forwardedProps` (**demo only**, see below) |
| run the graph | `app.stream(..., stream_mode="updates")` | adapter: `app.astream_events(...)` |
| show tool calls | `print("[tool call] ...")` | `TOOL_CALL_*` events → tool cards |
| show the answer | `print(reply)` | `TEXT_MESSAGE_*` events, streamed token by token |
| checkpointer | `SqliteSaver` | `AsyncSqliteSaver` (adapter is async), **same file** |
| graph, memory, tools, skills | `build_graph()` | **the same `build_graph()`** |

Because both use `checkpoints.db` and `memories.db`, a fact saved in the
terminal is recalled in the browser for the same user, and vice versa.

### 6.3 Points to stress with students

- **The graph didn't change.** AG-UI and CopilotKit replaced only the outer
  loop: input, output and transport.
- **Why a runtime in the middle?** The browser talks to its own origin; the
  agent URL and any secrets stay server-side, and the runtime is where auth
  would go.
- **Identity is a server decision.** Here the browser picks `user_id` so the
  demo can switch users. A real app derives it from the login session on the
  server and never trusts a value sent by the browser; otherwise anyone can
  read anyone's memories.
- **The frontend sends the whole message list; the checkpointer is still the
  source of truth.** The adapter merges by message id, so nothing is
  duplicated.
