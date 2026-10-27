// Hybrid client: OUR AG-UI loop (@ag-ui/client) + CopilotKit's chat COMPONENTS. No runtime, no Next.js.
//
//   browser ── /agent, /inventory (same origin) ──► proxy ──► FastAPI :8001
//   proxy = Vite's dev server (vite.config.ts) in development, nginx (deploy/nginx.conf) in production
//
//   HttpAgent (@ag-ui/client)   POSTs RunAgentInput to :8001/agent, applies the SSE events to
//                               agent.messages / agent.state, and tells us through subscribe()
//   CopilotChatView             draws messages + input; it only renders what we pass in
//   PlanPanel / ApproveCard     our own components, fed by agent.state and RUN_FINISHED.outcome
//
// CopilotKitProvider is still required: the message view reads its tool renderers from the
// provider's context. We hand it our agent as a local agent, so it never looks for a runtime.

import { useEffect, useMemo, useState } from "react";
import { HttpAgent, type Interrupt, type Message } from "@ag-ui/client";
import { CopilotChatView, CopilotKitProvider, useDefaultRenderTool } from "@copilotkit/react-core/v2";

// same origin: the dev proxy (vite.config.ts) or nginx (deploy/nginx.conf) routes it to FastAPI
const AGENT_URL = import.meta.env.VITE_AGENT_URL ?? "/agent";
const SERVER_URL = AGENT_URL.replace(/\/agent$/, ""); // "" -> /inventory on the same origin

type Action = { op: string; name: string; kind: string; status: string; attempts: number; cloud_id: string | null; error: string | null };
type ProvisionState = {
  phase?: string;
  plan?: { env: string; region: string; destroy: boolean; budget_usd?: number | null } | null;
  cost?: { lines: Record<string, number>; total: number } | null;
  issues?: string[];
  actions?: Action[];
};
type Row = { name: string; kind: string; env: string; region: string; cloud_id: string };

const newThreadId = () => crypto.randomUUID().slice(0, 8);
const ICON: Record<string, string> = { ready: "✓", deleted: "✓", retrying: "↻", failed: "✗", pending: "·" };

export default function App() {
  const [thread, setThread] = useState(newThreadId);
  // key: a new thread gets a fresh agent, fresh messages and fresh state
  return <Workspace key={thread} thread={thread} onNewThread={() => setThread(newThreadId())} />;
}

function Workspace({ thread, onNewThread }: { thread: string; onNewThread: () => void }) {
  const agent = useMemo(() => new HttpAgent({ url: AGENT_URL, threadId: thread }), [thread]);
  const agents = useMemo(() => ({ default: agent }), [agent]);

  const [messages, setMessages] = useState<Message[]>([]);
  const [state, setState] = useState<ProvisionState>({});
  const [running, setRunning] = useState(false);
  const [pending, setPending] = useState<Interrupt | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState(0); // bumps after every run so the inventory refreshes

  // AG-UI events -> React state. HttpAgent has already applied each event to agent.messages /
  // agent.state; we copy them so React re-renders.
  useEffect(() => {
    const sub = agent.subscribe({
      onMessagesChanged: ({ messages }) => setMessages([...messages]),
      onStateChanged: ({ state }) => setState({ ...(state as ProvisionState) }),
      onRunFinishedEvent: ({ event }) => {
        if (event.outcome?.type === "interrupt") setPending(event.outcome.interrupts[0]); // graph paused in approve()
      },
      onRunFailed: ({ error }) => setError(error.message),
    });
    return () => sub.unsubscribe();
  }, [agent]);

  async function run(params: Parameters<HttpAgent["runAgent"]>[0]) {
    setRunning(true);
    setError(null);
    try {
      await agent.runAgent(params); // sends agent.messages + agent.state, streams events back
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(false);
      setRuns((n) => n + 1);
    }
  }

  function send(text: string) {
    if (running || pending) return;
    agent.addMessage({ id: crypto.randomUUID(), role: "user", content: text });
    run({});
  }

  function decide(approved: boolean, reason: string) {
    if (!pending) return;
    const interruptId = pending.id;
    setPending(null);
    // same thread + resume[]: the Python adapter turns it into Command(resume=payload)
    run({ resume: [{ interruptId, status: "resolved", payload: approved ? { approved: true } : { approved: false, reason } }] });
  }

  return (
    <CopilotKitProvider agents__unsafe_dev_only={agents}>
      <ToolCards />
      <div className="page">
        <div className="bar">
          <b>Cloud provisioner · hybrid</b>
          <span>
            thread <code>{thread}</code>
          </span>
          <button onClick={onNewThread} disabled={running}>
            New thread
          </button>
          <span className="hint">@ag-ui/client + CopilotKit components · no runtime · {AGENT_URL} via proxy → FastAPI</span>
        </div>
        <div className="workspace">
          <CopilotChatView
            className="chat"
            messages={messages}
            isRunning={running}
            onSubmitMessage={send}
            onStop={() => agent.abortRun()}
          />
          <aside className="side">
            {error && <div className="panel issues">{error}</div>}
            {pending && <ApproveCard message={pending.message ?? "Approve this plan?"} destroy={!!state.plan?.destroy} onDecide={decide} />}
            <PlanPanel state={state} running={running} />
            <Inventory refreshKey={runs} />
          </aside>
        </div>
      </div>
    </CopilotKitProvider>
  );
}

// every tool call in the chat becomes a small card (renderer lives in the provider's context)
function ToolCards() {
  useDefaultRenderTool({
    render: ({ name, parameters, status, result }) => (
      <div className="tool">
        <b>{status === "complete" ? "✓" : "…"} {name}</b>
        {name === "propose_plan" ? ` (${(parameters as { resources?: unknown[] })?.resources?.length ?? "…"} resources)` : `(${JSON.stringify(parameters)})`}
        {result && <div className="tool-result">{result.slice(0, 220)}</div>}
      </div>
    ),
  });
  return null;
}

function ApproveCard({ message, destroy, onDecide }: { message: string; destroy: boolean; onDecide: (approved: boolean, reason: string) => void }) {
  const [reason, setReason] = useState("");
  return (
    <div className={`approve ${destroy ? "danger" : ""}`}>
      <div className="approve-title">⏸ Approval needed</div>
      <p>{message}</p>
      <p className="muted">The graph is paused in approve(). Review the plan below; nothing changes until you decide.</p>
      <input placeholder="reason (if rejecting)" value={reason} onChange={(e) => setReason(e.target.value)} />
      <div className="approve-buttons">
        <button className="yes" onClick={() => onDecide(true, "")}>
          Approve
        </button>
        <button onClick={() => onDecide(false, reason)}>Reject</button>
      </div>
    </div>
  );
}

function PlanPanel({ state, running }: { state: ProvisionState; running: boolean }) {
  const { plan, cost, issues = [], actions = [], phase } = state;
  if (!plan && !issues.length) return <section className="panel muted">No plan yet. Describe what you need in the chat.</section>;
  const next = running && phase === "applying" ? actions.find((a) => a.status === "pending" || a.status === "retrying") : undefined;
  return (
    <section className="panel">
      <div className="panel-head">
        <b>{plan?.destroy ? "Destroy" : "Plan"}{plan ? ` · ${plan.env} · ${plan.region}` : ""}</b>
        <span className={`phase ${phase}`}>{phase}</span>
      </div>
      {issues.length > 0 && (
        <ul className="issues">
          {issues.map((i) => <li key={i}>{i}</li>)}
        </ul>
      )}
      <table>
        <tbody>
          {actions.map((a) => (
            <tr key={a.name} className={a.status}>
              <td>{a === next ? "…" : ICON[a.status] ?? "·"}</td>
              <td>{a.op}</td>
              <td>{a.kind}</td>
              <td>{a.name}{a.error && <div className="err">{a.error.slice(0, 80)}</div>}</td>
              <td className="num">{cost ? `$${(cost.lines[a.name] ?? 0).toFixed(2)}` : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {cost && (
        <div className="total">
          {plan?.destroy ? "saves" : "total"} <b>${cost.total.toFixed(2)}</b>/month
          {plan?.budget_usd ? <span className="muted"> · budget ${plan.budget_usd}</span> : null}
        </div>
      )}
    </section>
  );
}

function Inventory({ refreshKey }: { refreshKey: number }) {
  const [data, setData] = useState<{ provider: string; resources: Row[] } | null>(null);
  useEffect(() => {
    fetch(`${SERVER_URL}/inventory`).then((r) => r.json()).then(setData).catch(() => setData(null));
  }, [refreshKey]);
  return (
    <section className="panel">
      <div className="panel-head">
        <b>Inventory</b>
        <span className="muted">{data ? `${data.provider} cloud` : "server offline"}</span>
      </div>
      {data && data.resources.length === 0 && <div className="muted">nothing provisioned</div>}
      <table>
        <tbody>
          {data?.resources.map((r) => (
            <tr key={r.name}>
              <td>{r.env}</td>
              <td>{r.kind}</td>
              <td>{r.name}</td>
              <td className="muted">{r.cloud_id}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
