// The only file that touches @assistant-ui/react-ag-ui. Its interrupt hooks are new and change often;
// the rest of the app uses usePendingInterrupt() and useProvisionState() from here.
//
//   HttpAgent (@ag-ui/client)   POST /agent, SSE back; one per thread
//   useAgUiRuntime              turns AG-UI events into assistant-ui messages, tool parts, interrupts
//   getRunContext               the A2UI catalog on every run (new message, resume): a2ui.enabled() checks for it

import { useMemo, useState, type ReactNode } from "react";
import { HttpAgent } from "@ag-ui/client";
import { AssistantRuntimeProvider, useAuiEvent } from "@assistant-ui/react";
import {
  useAgUiInterrupts,
  useAgUiRuntime,
  useAgUiState,
  useAgUiSubmitInterruptResponses,
  type AgUiInterrupt,
} from "@assistant-ui/react-ag-ui";
import { A2UI_CONTEXT } from "@/a2ui/catalog";
import type { ProvisionState } from "@/components/ProvisionPanels";

const RUN_CONTEXT = () => [A2UI_CONTEXT];

export function ProvisionRuntime({ url, threadId, children }: { url: string; threadId: string; children: ReactNode }) {
  const agent = useMemo(() => new HttpAgent({ url, threadId }), [url, threadId]);
  const runtime = useAgUiRuntime({
    agent,
    getRunContext: RUN_CONTEXT,
    // a resume carries the whole transcript, like web_shadcn; the server keeps graph state from its checkpoint
    resumeTranscript: "full",
    // one graph run = several LLM turns (agent -> tool -> agent), so the closing MESSAGES_SNAPSHOT has several
    // assistant messages. Unjoined, the last one shows an open propose_plan call as a pending *client* tool and
    // the interrupt (kept on the run's own message) is not "pending": no approval card. Joined, it's one message.
    joinStrategy: "concat-content",
  });
  return <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>;
}

/** The last STATE_SNAPSHOT (display only: the server never takes state from the browser). */
export function useProvisionState(): ProvisionState {
  return useAgUiState<ProvisionState>() ?? {};
}

/** Bumps when a run ends (finished, paused or failed), e.g. to refresh the inventory. */
export function useRunCount(): number {
  const [n, setN] = useState(0);
  useAuiEvent("thread.runEnd", () => setN((x) => x + 1));
  return n;
}

/**
 * The open interrupt, if any. Our graph pauses at one place at a time; the runtime requires an answer
 * for every open interrupt, so more than one is reported as an error instead of being half-answered.
 */
export function usePendingInterrupt() {
  const interrupts = useAgUiInterrupts();
  const submit = useAgUiSubmitInterruptResponses();
  const pending: AgUiInterrupt | null = interrupts.length === 1 ? interrupts[0] : null;
  const error = interrupts.length > 1 ? `the agent opened ${interrupts.length} interrupts; this client answers one at a time` : null;

  function resolve(payload: unknown) {
    if (!pending) return Promise.resolve();
    return submit([{ interruptId: pending.id, status: "resolved", payload }]);
  }

  return { pending, error, resolve };
}

/** The value the graph passed to interrupt(); ag-ui-langgraph puts it in metadata.langgraph.raw. */
export function interruptValue<T = Record<string, unknown>>(i: AgUiInterrupt): T | undefined {
  return (i.metadata as { langgraph?: { raw?: T } } | undefined)?.langgraph?.raw;
}
