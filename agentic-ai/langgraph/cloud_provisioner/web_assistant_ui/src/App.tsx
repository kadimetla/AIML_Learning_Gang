// assistant-ui + A2UI client. Same server, same A2UI renderer and panels as web_shadcn; assistant-ui
// replaces useAgUi + ChatView (the run loop and the chat).
//
//   browser ── /agent, /inventory (same origin) ──► Vite proxy / nginx ──► FastAPI :8001
//
//   ProvisionRuntime (agui/)   HttpAgent + useAgUiRuntime; the A2UI catalog via getRunContext
//   Thread (chat/)             assistant-ui primitives, shadcn look; tool parts drawn by name
//   A2UISurface (a2ui/)        A2UI ops -> catalog (catalog.tsx) -> shadcn components
//
// Where A2UI shows up (as in web_shadcn):
//   interrupt reason "a2ui:form"      the ask_details form, under the messages; its action resumes the graph
//   generate_a2ui tool result         an agent-designed view, inline; read-only (viewCatalog)
//   interrupt reason "plan:approval"  NOT A2UI: ApprovalCard, drawn from validated state

import { useMemo, useState } from "react";
import { useAuiState, type ToolCallMessagePartProps } from "@assistant-ui/react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { A2UISurface } from "@/a2ui/A2UISurface";
import { DomainData, formCatalog, viewCatalog } from "@/a2ui/catalog";
import { applyOps, opsFrom, type Surface } from "@/a2ui/surface";
import { interruptValue, ProvisionRuntime, usePendingInterrupt, useProvisionState, useRunCount } from "@/agui/runtime";
import { Thread } from "@/components/chat/Thread";
import { ApprovalCard, Inventory, PlanPanel, useInventory } from "@/components/ProvisionPanels";

const AGENT_URL = "/agent";
const newThreadId = () => crypto.randomUUID().slice(0, 8);

export default function App() {
  const [thread, setThread] = useState(newThreadId);
  return (
    <ProvisionRuntime key={thread} url={AGENT_URL} threadId={thread}>
      <Workspace thread={thread} onNewThread={() => setThread(newThreadId())} />
    </ProvisionRuntime>
  );
}

/** graph.py refuses a view that typed money amounts (costs come from PlanCost); a2ui.rejected() */
function viewRefused(value: unknown): boolean {
  try {
    return typeof value === "string" && JSON.parse(value)?.error === "view_rejected";
  } catch {
    return false;
  }
}

/** All surfaces in an a2ui_operations envelope (one per envelope in practice). */
function surfacesOf(value: unknown): Surface[] {
  const ops = opsFrom(value);
  return ops ? Object.values(applyOps({}, ops)) : [];
}

const asText = (r: unknown) => (r == null ? undefined : typeof r === "string" ? r : JSON.stringify(r));

/** generate_a2ui: an agent-designed view. Parsed once per result: surfaces must keep their identity. */
function GenerateA2UI({ result, status }: ToolCallMessagePartProps) {
  const text = asText(result);
  const surfaces = useMemo(() => surfacesOf(text), [text]);
  if (status.type === "running") return <p className="animate-pulse text-xs text-muted-foreground">designing a view…</p>;
  if (!surfaces.length) return <Badge variant="destructive">{viewRefused(text) ? "view refused by the server: it typed costs" : "could not build that view"}</Badge>;
  return surfaces.map((s) => <A2UISurface key={s.id} surface={s} catalog={viewCatalog} />);
}

/** Every other tool: a collapsible line with its result. */
function ToolLine({ toolName, args, result, status }: ToolCallMessagePartProps) {
  const done = status.type !== "running" && status.type !== "requires-action";
  const label =
    toolName === "propose_plan" ? `propose_plan · ${(args?.resources as unknown[] | undefined)?.length ?? "…"} resources`
    : toolName === "ask_details" ? (done ? "details received" : "waiting for the form")
    : toolName;
  const text = asText(result);
  return (
    <details className="group rounded-md border bg-muted/40 px-2.5 py-1.5 text-xs">
      <summary className="flex cursor-pointer list-none items-center gap-2">
        <span>{done ? "✓" : "…"}</span>
        <span className="font-medium">{label}</span>
      </summary>
      {text && <pre className="mt-1.5 max-h-40 overflow-auto whitespace-pre-wrap text-muted-foreground">{text.slice(0, 1200)}</pre>}
    </details>
  );
}

const TOOLS = {
  generate_a2ui: GenerateA2UI,
  render_a2ui: () => null, // the sub-agent's inner call; its outer generate_a2ui shows the result
};

function Workspace({ thread, onNewThread }: { thread: string; onNewThread: () => void }) {
  const state = useProvisionState();
  const runs = useRunCount();
  const inventory = useInventory(runs);
  const running = useAuiState((s) => s.thread.isRunning);
  const { pending, error, resolve } = usePendingInterrupt();

  // keyed on the interrupt: a re-render must not rebuild the form (it would reset what the user typed)
  const form = useMemo(() => (pending?.reason === "a2ui:form" ? surfacesOf(interruptValue(pending)) : []), [pending]);
  const approval = pending && pending.reason !== "a2ui:form" ? pending : null;

  return (
    <DomainData.Provider value={{ state, inventory }}>
      <div className="flex h-dvh flex-col bg-background text-foreground">
        <header className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5">
          <b className="text-sm">Cloud provisioner</b>
          <Badge variant="outline">assistant-ui + A2UI</Badge>
          <span className="text-xs text-muted-foreground">
            thread <code>{thread}</code>
          </span>
          <Button size="sm" variant="outline" onClick={onNewThread} disabled={running}>
            New thread
          </Button>
          <span className="ml-auto hidden text-xs text-muted-foreground md:inline">@assistant-ui/react-ag-ui · no runtime server · /agent via proxy → FastAPI</span>
        </header>
        <main className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[minmax(0,1fr)_380px]">
          <Thread
            tools={TOOLS}
            Fallback={ToolLine}
            disabled={!!pending}
            placeholder={pending ? "Answer the form or the approval first" : undefined}
            footer={form.map((s) => (
              // the graph is paused in details(); the form's action IS the resume payload
              <A2UISurface key={`${pending!.id}:${s.id}`} surface={s} catalog={formCatalog} onAction={(a) => resolve(a)} />
            ))}
          />
          <aside className="flex min-h-0 flex-col gap-3 overflow-y-auto border-t bg-muted/30 p-3 md:border-t-0 md:border-l">
            {error && <p className="rounded-md bg-destructive/10 p-2 text-xs text-destructive">{error}</p>}
            {approval && (
              <ApprovalCard
                message={approval.message ?? "Approve this plan?"}
                expiresAt={approval.expiresAt}
                destroy={!!state.plan?.destroy}
                onDecide={(approved, reason) => resolve(approved ? { approved: true } : { approved: false, reason })}
              />
            )}
            <PlanPanel state={state} running={running} />
            <Inventory data={inventory} />
          </aside>
        </main>
      </div>
    </DomainData.Provider>
  );
}
