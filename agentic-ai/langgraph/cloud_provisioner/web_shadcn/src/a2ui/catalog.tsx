// THE A2UI -> shadcn MAPPING. One entry per component type the agent may use.
//
//   renderers  how each type looks: shadcn components + Tailwind tokens (your design system)
//   SCHEMA     what each type means and takes; sent to the agent in RunAgentInput.context,
//              so the LLM can only ask for types that exist here (anything else -> <Unsupported/>)
//
// To add a type: add a renderer AND a schema entry. The agent learns about it on the next run.

import type { Context } from "@ag-ui/client";
import type { ComponentType, ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { Node } from "./surface";

export const CATALOG_ID = "cloud-provisioner/shadcn/v1"; // same id as a2ui.py

export type RenderCtx = {
  node: Node;
  disabled: boolean;
  value: (v: unknown) => unknown; // literal, or { path } resolved against the data model
  text: (v: unknown) => string;
  set: (path: string, v: unknown) => void; // two-way binding for inputs
  child: (id?: string) => ReactNode;
  children: () => ReactNode;
  fire: (n: Node) => void; // the node's action -> back to the agent
};

const JUSTIFY: Record<string, string> = { start: "justify-start", center: "justify-center", end: "justify-end", spaceBetween: "justify-between" };
const TEXT: Record<string, string> = {
  h1: "text-xl font-semibold tracking-tight",
  h2: "text-lg font-semibold tracking-tight",
  h3: "text-sm font-semibold",
  body: "text-sm",
  caption: "text-xs text-muted-foreground",
};
const BUTTON = { primary: "default", secondary: "outline", destructive: "destructive" } as const;
const BADGE = { default: "default", secondary: "secondary", outline: "outline", destructive: "destructive" } as const;

const path = (v: unknown) => (v && typeof v === "object" && "path" in v ? (v as { path: string }).path : null);
const id = (n: Node) => `a2ui-${n.id}`;

export const catalog: Record<string, ComponentType<RenderCtx>> = {
  Card: ({ child, children, node }) => (
    <Card className="gap-0 py-0">
      <CardContent className="flex flex-col gap-3 p-4">{node.child ? child(node.child) : children()}</CardContent>
    </Card>
  ),
  Column: ({ children }) => <div className="flex flex-col gap-3">{children()}</div>,
  Row: ({ children, node }) => (
    <div className={cn("flex flex-wrap items-center gap-2", JUSTIFY[node.justify as string] ?? "justify-start")}>{children()}</div>
  ),
  List: ({ children, node }) => (
    <div className={node.direction === "horizontal" ? "grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3" : "flex flex-col gap-2"}>
      {children()}
    </div>
  ),
  Text: ({ node, text }) => <p className={TEXT[node.variant as string] ?? TEXT.body}>{text(node.text)}</p>,
  Badge: ({ node, text }) => <Badge variant={BADGE[node.variant as keyof typeof BADGE] ?? "secondary"}>{text(node.text)}</Badge>,
  Divider: () => <Separator />,
  KeyValue: ({ node, text }) => (
    <div className="flex items-baseline justify-between gap-4 text-sm">
      <span className="text-muted-foreground">{text(node.label)}</span>
      <span className="font-medium tabular-nums">{text(node.value)}</span>
    </div>
  ),
  TextField: ({ node, text, set, disabled }) => {
    const p = path(node.value);
    const common = { id: id(node), value: text(node.value), disabled: disabled || !p, onChange: (e: { target: { value: string } }) => p && set(p, e.target.value) };
    return (
      <div className="grid gap-1.5">
        <Label htmlFor={id(node)}>{text(node.label)}</Label>
        {node.variant === "longText" ? <Textarea rows={2} {...common} /> : <Input type={node.variant === "number" ? "number" : "text"} {...common} />}
      </div>
    );
  },
  ChoicePicker: ({ node, text, set, disabled }) => {
    const p = path(node.value);
    const options = Array.isArray(node.options) ? (node.options as { label: string; value: string }[]) : [];
    return (
      <div className="grid gap-1.5">
        <Label htmlFor={id(node)}>{text(node.label)}</Label>
        <Select value={text(node.value) || undefined} onValueChange={(v) => p && set(p, v)} disabled={disabled || !p}>
          <SelectTrigger id={id(node)} className="w-full">
            <SelectValue placeholder="Choose…" />
          </SelectTrigger>
          <SelectContent>
            {options.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    );
  },
  CheckBox: ({ node, value, text, set, disabled }) => {
    const p = path(node.value);
    return (
      <div className="flex items-center gap-2">
        <Checkbox id={id(node)} checked={value(node.value) === true} onCheckedChange={(c) => p && set(p, c === true)} disabled={disabled || !p} />
        <Label htmlFor={id(node)}>{text(node.label)}</Label>
      </div>
    );
  },
  Button: ({ node, child, fire, disabled }) => (
    <Button size="sm" variant={BUTTON[node.variant as keyof typeof BUTTON] ?? "outline"} disabled={disabled || !node.action} onClick={() => fire(node)}>
      {child(node.child)}
    </Button>
  ),
};

/** Shown instead of a type the catalog doesn't have: the agent can't invent components. */
export function Unsupported({ type }: { type: string }) {
  return <p className="rounded border border-dashed px-2 py-1 text-xs text-muted-foreground">unsupported component: {type}</p>;
}

// What the agent is told. Keep it in step with the renderers above.
const dyn = "string, or {path} bound to the data model";
const SCHEMA = {
  catalogId: CATALOG_ID,
  components: [
    { name: "Card", props: { child: "id" }, description: "bordered box; use as root" },
    { name: "Column", props: { children: "id[]" }, description: "vertical stack" },
    { name: "Row", props: { children: "id[]", justify: "start|center|end|spaceBetween" }, description: "horizontal stack" },
    { name: "List", props: { children: "{componentId, path} template, repeated per array item", direction: "vertical|horizontal" }, description: "repeat a template over /items; paths inside are relative" },
    { name: "Text", props: { text: dyn, variant: "h1|h2|h3|body|caption" }, description: "text" },
    { name: "Badge", props: { text: dyn, variant: "default|secondary|outline|destructive" }, description: "small status label" },
    { name: "KeyValue", props: { label: dyn, value: dyn }, description: "one label/value line, e.g. a price" },
    { name: "Divider", props: {}, description: "separator line" },
    { name: "TextField", props: { label: dyn, value: "{path} (required to be editable)", variant: "shortText|longText|number" }, description: "text input" },
    { name: "ChoicePicker", props: { label: dyn, options: "[{label, value}]", value: "{path}" }, description: "pick one option" },
    { name: "CheckBox", props: { label: dyn, value: "{path} boolean" }, description: "checkbox" },
    { name: "Button", props: { child: "id of a Text", variant: "primary|secondary|destructive", action: "{event: {name, context: {key: {path}}}}" }, description: "sends an action to the agent" },
  ],
};

// The description must match ag-ui's A2UI_SCHEMA_CONTEXT_DESCRIPTION exactly: that is how
// ag-ui-langgraph recognises this entry and moves it to state["ag-ui"]["a2ui_schema"].
export const A2UI_CONTEXT: Context = {
  description:
    "A2UI Component Schema — available components for generating UI surfaces. Use these component names and properties when creating A2UI operations.",
  value: JSON.stringify(SCHEMA),
};
