// shadcn + A2UI client. No CopilotKit, no runtime: useAgUi talks AG-UI, shadcn draws everything.
//
//   browser ── /agent, /inventory (same origin) ──► Vite proxy / nginx ──► FastAPI :8001
//
//   useAgUi (agui/)        AG-UI run loop; sends the A2UI catalog schema as context on every run
//   ChatView (chat/)       shadcn chat; renderTool slot draws each tool call
//   A2UISurface (a2ui/)    A2UI ops -> catalog (catalog.tsx) -> shadcn components
//
// Where A2UI shows up:
//   interrupt reason "a2ui:form"   the ask_details form, above the input; its action resumes the graph
//   generate_a2ui tool result      an agent-designed view, inline in the chat; its actions become messages
//   interrupt reason "plan:approval"  NOT A2UI: ApprovalCard, drawn from validated state

import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { A2UISurface } from "@/a2ui/A2UISurface";
import { A2UI_CONTEXT } from "@/a2ui/catalog";
import { applyOps, opsFrom, type Surface, type UserAction } from "@/a2ui/surface";
import { interruptValue, useAgUi } from "@/agui/useAgUi";
import { ChatView, type ToolView } from "@/components/chat/ChatView";
import { ApprovalCard, Inventory, PlanPanel, type ProvisionState } from "@/components/ProvisionPanels";

const AGENT_URL = "/agent";
const CONTEXT = [A2UI_CONTEXT];
const newThreadId = () => crypto.randomUUID().slice(0, 8);

export default function App() {
  const [thread, setThread] = useState(newThreadId);
  return <Workspace key={thread} thread={thread} onNewThread={() => setThread(newThreadId())} />;
}

/** All surfaces in an a2ui_operations envelope (one per envelope in practice). */
function surfacesOf(value: unknown): Surface[] {
  const ops = opsFrom(value);
  return ops ? Object.values(applyOps({}, ops)) : [];
}

/** A generate_a2ui result. Parsed once per result: surfaces must keep their identity across renders. */
function ResultView({ result, onAction, disabled }: { result?: string; onAction: (a: UserAction) => void; disabled: boolean }) {
  const surfaces = useMemo(() => surfacesOf(result), [result]);
  if (!surfaces.length) return <Badge variant="destructive">could not build that view</Badge>;
  return surfaces.map((s) => <A2UISurface key={s.id} surface={s} onAction={onAction} disabled={disabled} />);
}

function Workspace({ thread, onNewThread }: { thread: string; onNewThread: () => void }) {
  const chat = useAgUi<ProvisionState>(AGENT_URL, thread, CONTEXT);
  const { pending, state } = chat;

  const form = useMemo(() => (pending?.reason === "a2ui:form" ? surfacesOf(interruptValue(pending)) : []), [pending]);
  const approval = pending && pending.reason !== "a2ui:form" ? pending : null;

  // a button in an inline (generate_a2ui) view: tell the agent in a message
  const onViewAction = ({ action }: UserAction) =>
    chat.send(`[clicked "${action.name}" in ${action.surfaceId}] ${JSON.stringify(action.context)}`);

  function renderTool({ call, args, result, done }: ToolView) {
    const name = call.function.name;
    if (name === "render_a2ui") return null; // the sub-agent's inner call; its outer generate_a2ui shows the result
    if (name === "generate_a2ui") {
      if (!done) return <p className="animate-pulse text-xs text-muted-foreground">designing a view…</p>;
      return <ResultView result={result} onAction={onViewAction} disabled={chat.running} />;
    }
    const label =
      name === "propose_plan" ? `propose_plan · ${(args.resources as unknown[] | undefined)?.length ?? "…"} resources`
      : name === "ask_details" ? (done ? "details received" : "waiting for the form")
      : name;
    return (
      <details className="group rounded-md border bg-muted/40 px-2.5 py-1.5 text-xs">
        <summary className="flex cursor-pointer list-none items-center gap-2">
          <span>{done ? "✓" : "…"}</span>
          <span className="font-medium">{label}</span>
        </summary>
        {result && <pre className="mt-1.5 max-h-40 overflow-auto whitespace-pre-wrap text-muted-foreground">{result.slice(0, 1200)}</pre>}
      </details>
    );
  }

  return (
    <div className="flex h-dvh flex-col bg-background text-foreground">
      <header className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5">
        <b className="text-sm">Cloud provisioner</b>
        <Badge variant="outline">shadcn + A2UI</Badge>
        <span className="text-xs text-muted-foreground">
          thread <code>{thread}</code>
        </span>
        <Button size="sm" variant="outline" onClick={onNewThread} disabled={chat.running}>
          New thread
        </Button>
        <span className="ml-auto hidden text-xs text-muted-foreground md:inline">@ag-ui/client · no runtime · /agent via proxy → FastAPI</span>
      </header>
      <main className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[minmax(0,1fr)_380px]">
        <ChatView
          messages={chat.messages}
          running={chat.running}
          disabled={!!pending}
          placeholder={pending ? "Answer the form or the approval first" : undefined}
          onSend={chat.send}
          onStop={chat.stop}
          renderTool={renderTool}
          footer={form.map((s) => (
            // the graph is paused in details(); the form's action IS the resume payload
            <A2UISurface key={`${pending!.id}:${s.id}`} surface={s} onAction={(a) => chat.resolve(a)} />
          ))}
        />
        <aside className="flex min-h-0 flex-col gap-3 overflow-y-auto border-t bg-muted/30 p-3 md:border-t-0 md:border-l">
          {chat.error && <p className="rounded-md bg-destructive/10 p-2 text-xs text-destructive">{chat.error}</p>}
          {approval && (
            <ApprovalCard
              message={approval.message ?? "Approve this plan?"}
              expiresAt={approval.expiresAt}
              destroy={!!state.plan?.destroy}
              onDecide={(approved, reason) => chat.resolve(approved ? { approved: true } : { approved: false, reason })}
            />
          )}
          <PlanPanel state={state} running={chat.running} />
          <Inventory refreshKey={chat.runs} />
        </aside>
      </main>
    </div>
  );
}
