"use client";

// The whole UI: a user picker, a thread id, and CopilotKit's chat component.
//
//   user_id   -> CopilotKitProvider `properties` -> AG-UI forwardedProps -> server.py -> graph config
//   thread_id -> CopilotChat `threadId`          -> AG-UI threadId       -> checkpointer
//
// Same two keys as chat.py's --user and /new, just set from the browser.

import { useEffect, useState } from "react";
import { CopilotChat, CopilotKitProvider, useDefaultRenderTool } from "@copilotkit/react-core/v2";

const USERS = ["adi", "sam", "demo"];
const newThreadId = () => crypto.randomUUID().slice(0, 8);

export default function Page() {
  const [user, setUser] = useState(USERS[0]);
  const [thread, setThread] = useState("");
  useEffect(() => setThread(newThreadId()), []); // browser only: avoids an SSR/hydration mismatch

  return (
    <div className="page">
      <div className="bar">
        <label>
          user{" "}
          <select
            value={user}
            onChange={(e) => {
              setUser(e.target.value);
              setThread(newThreadId()); // a thread belongs to one user
            }}
          >
            {USERS.map((u) => (
              <option key={u}>{u}</option>
            ))}
          </select>
        </label>
        <span>
          thread <code>{thread}</code>
        </span>
        <button onClick={() => setThread(newThreadId())}>New thread</button>
        <span>new thread = history gone, memories stay</span>
      </div>
      {/* key: remount the chat so the old thread's messages are cleared from the screen */}
      {thread && (
        <CopilotKitProvider key={`${user}/${thread}`} runtimeUrl="/api/copilotkit" properties={{ user_id: user }}>
          <Chat thread={thread} />
        </CopilotKitProvider>
      )}
    </div>
  );
}

// Every AG-UI TOOL_CALL_* event for ANY tool ("*") is drawn as a small card, so
// students can watch the agent loop: load_skill -> lookup_order -> ... -> answer.
function Chat({ thread }: { thread: string }) {
  useDefaultRenderTool({
    render: ({ name, parameters, status, result }) => (
      <div className="tool">
        <b>{status === "complete" ? "✓" : "…"} {name}</b>({JSON.stringify(parameters)})
        {result && <div className="tool-result">{result.slice(0, 160)}</div>}
      </div>
    ),
  });
  return <CopilotChat className="chat" threadId={thread} />;
}
