// CopilotKit runtime: the browser talks to this route, and this route talks
// AG-UI to our Python agent. It holds no AI logic; it only forwards.
//
//   CopilotChat --(CopilotKit protocol)--> /api/copilotkit/* --(AG-UI over SSE)--> :8000/agent

import { HttpAgent } from "@ag-ui/client";
import { CopilotRuntime, createCopilotRuntimeHandler } from "@copilotkit/runtime/v2";

const AGENT_URL = process.env.AGENT_URL ?? "http://127.0.0.1:8000/agent";

const runtime = new CopilotRuntime({
  agents: {
    default: new HttpAgent({ url: AGENT_URL }), // "default" = the agent CopilotChat uses
  },
});

const handler = createCopilotRuntimeHandler({ runtime, basePath: "/api/copilotkit" });

export const GET = handler;
export const POST = handler;
