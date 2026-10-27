// shadcn chat view: draws messages + input. Presentational only (like CopilotChatView): it never
// talks to the agent, it gets messages and callbacks as props.
//
//   renderTool  how a tool call looks (slot); the app decides, e.g. an A2UI surface for generate_a2ui
//   footer      anything shown above the input (slot); the app puts the A2UI form here

import { useEffect, useRef, useState, type ReactNode } from "react";
import Markdown from "react-markdown";
import type { Message, ToolCall } from "@ag-ui/client";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

export type ToolView = { call: ToolCall; args: Record<string, unknown>; result?: string; done: boolean };

type Props = {
  messages: Message[];
  running: boolean;
  disabled?: boolean;
  placeholder?: string;
  onSend: (text: string) => void;
  onStop: () => void;
  renderTool: (t: ToolView) => ReactNode;
  footer?: ReactNode;
};

function parseArgs(s: string): Record<string, unknown> {
  try {
    return JSON.parse(s || "{}");
  } catch {
    return {}; // still streaming: the arguments are partial JSON
  }
}

export function ChatView({ messages, running, disabled, placeholder, onSend, onStop, renderTool, footer }: Props) {
  const [text, setText] = useState("");
  const bottom = useRef<HTMLDivElement>(null);
  const scroller = useRef<HTMLDivElement>(null);

  // tool results arrive as separate role:"tool" messages; pair them with their call by id
  const results = new Map<string, string>();
  for (const m of messages) if (m.role === "tool") results.set(m.toolCallId, typeof m.content === "string" ? m.content : "");

  // follow the stream, unless the user scrolled up to read
  useEffect(() => {
    const el = scroller.current;
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 160) bottom.current?.scrollIntoView({ block: "end" });
  }, [messages, footer]);

  function submit() {
    if (!text.trim() || running || disabled) return;
    onSend(text);
    setText("");
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <div className="mx-auto flex max-w-2xl flex-col gap-3">
          {messages.length === 0 && (
            <p className="py-10 text-center text-sm text-muted-foreground">Describe the infrastructure you need, e.g. "a small web app with a database".</p>
          )}
          {messages.map((m) => {
            if (m.role === "user")
              return (
                <div key={m.id} className="ml-auto max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-3.5 py-2 text-sm text-primary-foreground whitespace-pre-wrap">
                  {typeof m.content === "string" ? m.content : ""}
                </div>
              );
            if (m.role !== "assistant") return null;
            return (
              <div key={m.id} className="flex max-w-full flex-col gap-2">
                {m.content && (
                  <div className="prose-chat text-sm leading-relaxed">
                    <Markdown>{m.content}</Markdown>
                  </div>
                )}
                {m.toolCalls?.map((call) =>
                  <div key={call.id}>{renderTool({ call, args: parseArgs(call.function.arguments), result: results.get(call.id), done: results.has(call.id) })}</div>
                )}
              </div>
            );
          })}
          {running && <p className="animate-pulse text-xs text-muted-foreground">working…</p>}
          {footer}
          <div ref={bottom} />
        </div>
      </div>
      <form
        className="border-t bg-background p-3"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <div className="mx-auto flex max-w-2xl items-end gap-2">
          <Textarea
            value={text}
            rows={1}
            disabled={disabled}
            placeholder={placeholder ?? "Message the provisioning agent"}
            className={cn("max-h-40 min-h-10 resize-none")}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
          />
          {running ? (
            <Button type="button" variant="outline" onClick={onStop}>
              Stop
            </Button>
          ) : (
            <Button type="submit" disabled={disabled || !text.trim()}>
              Send
            </Button>
          )}
        </div>
      </form>
    </div>
  );
}
