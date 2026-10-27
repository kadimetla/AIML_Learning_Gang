// The chat, built from assistant-ui primitives and styled with shadcn/Tailwind. assistant-ui owns the
// message list, streaming, auto-scroll, the composer and stop; this file only decides the look.
//
//   tools     how each tool call looks, by name (the app passes an A2UI surface for generate_a2ui)
//   footer    shown under the messages (the app puts the A2UI form here)
//
// No retry / edit buttons: both send a shorter transcript, and ag-ui-langgraph then forks the thread
// from an earlier checkpoint. Add them only after testing that around a pause.

import type { ReactNode } from "react";
import Markdown from "react-markdown";
import {
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  type TextMessagePartProps,
  type ToolCallMessagePartComponent,
} from "@assistant-ui/react";
import { Button } from "@/components/ui/button";

type Props = {
  tools: Record<string, ToolCallMessagePartComponent>;
  Fallback: ToolCallMessagePartComponent;
  footer?: ReactNode;
  disabled?: boolean;
  placeholder?: string;
};

function Text({ text }: TextMessagePartProps) {
  return (
    <div className="prose-chat text-sm leading-relaxed">
      <Markdown>{text}</Markdown>
    </div>
  );
}

export function Thread({ tools, Fallback, footer, disabled, placeholder }: Props) {
  const components = { Text, tools: { by_name: tools, Fallback } };
  return (
    <ThreadPrimitive.Root className="flex h-full min-h-0 flex-col">
      <ThreadPrimitive.Viewport className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <div className="mx-auto flex max-w-2xl flex-col gap-3">
          <ThreadPrimitive.Empty>
            <p className="py-10 text-center text-sm text-muted-foreground">Describe the infrastructure you need, e.g. "a small web app with a database".</p>
          </ThreadPrimitive.Empty>
          <ThreadPrimitive.Messages>
            {({ message }) =>
              message.role === "user" ? (
                <MessagePrimitive.Root className="ml-auto max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-3.5 py-2 text-sm whitespace-pre-wrap text-primary-foreground">
                  <MessagePrimitive.Parts />
                </MessagePrimitive.Root>
              ) : message.role === "assistant" ? (
                <MessagePrimitive.Root className="flex max-w-full flex-col gap-2">
                  <MessagePrimitive.Parts components={components} />
                </MessagePrimitive.Root>
              ) : null
            }
          </ThreadPrimitive.Messages>
          <ThreadPrimitive.If running>
            <p className="animate-pulse text-xs text-muted-foreground">working…</p>
          </ThreadPrimitive.If>
          {footer}
        </div>
      </ThreadPrimitive.Viewport>
      <ComposerPrimitive.Root className="border-t bg-background p-3">
        <div className="mx-auto flex max-w-2xl items-end gap-2">
          <ComposerPrimitive.Input
            rows={1}
            disabled={disabled}
            placeholder={placeholder ?? "Message the provisioning agent"}
            className="max-h-40 min-h-10 w-full flex-1 resize-none rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50"
          />
          <ThreadPrimitive.If running>
            <ComposerPrimitive.Cancel asChild>
              <Button type="button" variant="outline">
                Stop
              </Button>
            </ComposerPrimitive.Cancel>
          </ThreadPrimitive.If>
          <ThreadPrimitive.If running={false}>
            <ComposerPrimitive.Send asChild>
              <Button type="submit" disabled={disabled}>
                Send
              </Button>
            </ComposerPrimitive.Send>
          </ThreadPrimitive.If>
        </div>
      </ComposerPrimitive.Root>
    </ThreadPrimitive.Root>
  );
}
