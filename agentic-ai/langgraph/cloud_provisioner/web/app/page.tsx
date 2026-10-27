"use client";

// Chat on the left, the agent's live state on the right.
//
//   CopilotChat     messages + tool cards           (TEXT_MESSAGE_*, TOOL_CALL_* events)
//   PlanPanel       useAgent().agent.state          (STATE_SNAPSHOT: phase, plan, cost, issues, actions)
//   ApproveCard     useInterrupt -> resolve(...)    (graph paused in approve's interrupt(); resume[] continues it)
//   Inventory       GET /api/inventory              (what exists in the cloud now)

import { useEffect, useState } from "react";
import {
  CopilotChat,
  CopilotKitProvider,
  UseAgentUpdate,
  useAgent,
  useDefaultRenderTool,
  useInterrupt,
} from "@copilotkit/react-core/v2";

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

export default function Page() {
  const [thread, setThread] = useState("");
  useEffect(() => setThread(newThreadId()), []); // browser only: avoids an SSR/hydration mismatch

  return (
    <div className="page">
      <div className="bar">
        <b>Cloud provisioner</b>
        <span>
          thread <code>{thread}</code>
        </span>
        <button onClick={() => setThread(newThreadId())}>New thread</button>
        <span className="hint">try: “staging web app in us-east-1, 2 servers + postgres, under $60/month”</span>
      </div>
      {thread && (
        <CopilotKitProvider key={thread} runtimeUrl="/api/copilotkit">
          <Workspace thread={thread} />
        </CopilotKitProvider>
      )}
    </div>
  );
}

function Workspace({ thread }: { thread: string }) {
  const { agent } = useAgent({ updates: [UseAgentUpdate.OnStateChanged, UseAgentUpdate.OnRunStatusChanged] });
  const state = (agent.state ?? {}) as ProvisionState;

  // every tool call becomes a small card in the chat
  useDefaultRenderTool({
    render: ({ name, parameters, status, result }) => (
      <div className="tool">
        <b>{status === "complete" ? "✓" : "…"} {name}</b>
        {name === "propose_plan" ? ` (${(parameters as { resources?: unknown[] })?.resources?.length ?? "…"} resources)` : `(${JSON.stringify(parameters)})`}
        {result && <div className="tool-result">{result.slice(0, 220)}</div>}
      </div>
    ),
  });

  // the graph is paused inside approve(): show a card, resume with the decision
  useInterrupt({
    render: ({ interrupt, resolve }) => <ApproveCard message={interrupt?.message ?? "Approve this plan?"} state={state} resolve={resolve} />,
  });

  return (
    <div className="workspace">
      <CopilotChat className="chat" threadId={thread} />
      <aside className="side">
        <PlanPanel state={state} running={agent.isRunning} />
        <Inventory refreshKey={`${state.phase}-${agent.isRunning}`} />
      </aside>
    </div>
  );
}

function ApproveCard({ message, state, resolve }: { message: string; state: ProvisionState; resolve: (v: unknown) => unknown }) {
  const [reason, setReason] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  if (sent) return <div className="approve done">{sent}</div>;
  return (
    <div className={`approve ${state.plan?.destroy ? "danger" : ""}`}>
      <div className="approve-title">⏸ Approval needed</div>
      <p>{message}</p>
      <p className="muted">Review the plan on the right. Nothing changes until you approve.</p>
      <input placeholder="reason (if rejecting)" value={reason} onChange={(e) => setReason(e.target.value)} />
      <div className="approve-buttons">
        <button className="yes" onClick={() => { setSent("✓ approved"); resolve({ approved: true }); }}>
          Approve
        </button>
        <button onClick={() => { setSent(`✗ rejected${reason ? ": " + reason : ""}`); resolve({ approved: false, reason }); }}>
          Reject
        </button>
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

function Inventory({ refreshKey }: { refreshKey: string }) {
  const [data, setData] = useState<{ provider: string; resources: Row[] } | null>(null);
  useEffect(() => {
    fetch("/api/inventory").then((r) => r.json()).then(setData).catch(() => setData(null));
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
