// Headless AG-UI client: everything that talks to the agent, no UI. Any UI (shadcn here) renders
// what this hook returns. It plays the part CopilotKitProvider + useAgent + useInterrupt play in web/.
//
//   send(text)        add a user message, start a run
//   resolve(payload)  answer the open interrupt: same thread + resume[] -> Command(resume=payload)
//   context           sent with every run (here: the A2UI catalog, so the agent knows what it may draw)

import { useEffect, useMemo, useRef, useState } from "react";
import { HttpAgent, type Context, type Interrupt, type Message } from "@ag-ui/client";

export type AgUi<S extends object> = ReturnType<typeof useAgUi<S>>;

export function useAgUi<S extends object>(url: string, threadId: string, context: Context[] = []) {
  const agent = useMemo(() => new HttpAgent({ url, threadId }), [url, threadId]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [state, setState] = useState<S>({} as S);
  const [running, setRunning] = useState(false);
  const [pending, setPending] = useState<Interrupt | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState(0); // bumps after every run (e.g. to refresh side data)
  const contextRef = useRef(context);
  contextRef.current = context;

  // HttpAgent applies each SSE event to agent.messages / agent.state; copy them so React re-renders
  useEffect(() => {
    const sub = agent.subscribe({
      onMessagesChanged: ({ messages }) => setMessages([...messages]),
      onStateChanged: ({ state }) => setState({ ...(state as S) }),
      onRunFinishedEvent: ({ event }) => {
        if (event.outcome?.type === "interrupt") setPending(event.outcome.interrupts[0]); // the graph paused
      },
      onRunFailed: ({ error }) => setError(error.message),
    });
    return () => {
      sub.unsubscribe();
      // leaving this thread (new thread, unmount): close its stream. The server stops at its next
      // write; a step already running finishes, and the checkpointer keeps that consistent.
      agent.abortRun();
    };
  }, [agent]);

  async function run(params: Parameters<HttpAgent["runAgent"]>[0] = {}) {
    setRunning(true);
    setError(null);
    try {
      // sends agent.messages + agent.state (the last STATE_SNAPSHOT) + our context
      await agent.runAgent({ context: contextRef.current, ...params });
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(false);
      setRuns((n) => n + 1);
    }
  }

  function send(text: string) {
    if (running || pending || !text.trim()) return;
    agent.addMessage({ id: crypto.randomUUID(), role: "user", content: text });
    run();
  }

  function resolve(payload: unknown) {
    if (!pending) return;
    const interruptId = pending.id;
    setPending(null);
    run({ resume: [{ interruptId, status: "resolved", payload }] });
  }

  return { messages, state, running, pending, error, runs, send, resolve, stop: () => agent.abortRun() };
}

/** The value the graph passed to interrupt(); ag-ui-langgraph puts it in metadata.langgraph.raw. */
export function interruptValue<T = Record<string, unknown>>(i: Interrupt): T | undefined {
  return (i.metadata as { langgraph?: { raw?: T } } | undefined)?.langgraph?.raw;
}
