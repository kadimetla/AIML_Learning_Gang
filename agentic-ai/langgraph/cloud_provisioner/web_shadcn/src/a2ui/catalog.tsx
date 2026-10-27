// THE A2UI -> shadcn MAPPING. One entry per component type: a Zod schema for its props, and how it looks.
//
//   viewCatalog   what an LLM-made view (generate_a2ui) may use: read-only, no Button, no inputs.
//                 Same list as the server's a2ui.VIEW_CATALOG, which is what the agent is told.
//   formCatalog   viewCatalog + inputs + Button, for the form the server builds in code (ask_details)
//   schema        checked before drawing: a node with bad props draws <Invalid/>, never crashes the chat
//   unknown type  <Unsupported/>: the agent can't invent components
//
// InventoryTable and PlanCost take no numbers from the agent: they draw the server's inventory and the
// graph's priced plan (DomainData below), so an LLM-made view can't misstate a cost.
//
// To add a type: add an entry here AND to a2ui.VIEW_COMPONENTS (or only here, if just code-built forms use it).

import type { Context } from "@ag-ui/client";
import { createContext, useContext, type ComponentType, type ReactNode } from "react";
import { z } from "zod";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import type { InventoryData, ProvisionState } from "@/components/ProvisionPanels";
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

/** What the domain components draw: the app passes its live state and inventory down. */
export const DomainData = createContext<{ state: ProvisionState; inventory: InventoryData | null }>({ state: {}, inventory: null });

// prop types shared by the schemas
const Dyn = z.union([z.string().max(2000), z.number(), z.boolean(), z.object({ path: z.string() })]);
const Bound = z.object({ path: z.string() }); // inputs must be bound to the data model
const Ref = z.string();
const Children = z.union([z.array(Ref).max(200), z.object({ componentId: Ref, path: z.string() })]);
const props = <T extends z.ZodRawShape>(shape: T) => z.object({ id: z.string(), component: z.string(), ...shape });

type Entry = { schema: z.ZodObject; description: string; Render: ComponentType<RenderCtx & { props: never }> };

function entry<S extends z.ZodObject>(schema: S, description: string, Render: ComponentType<RenderCtx & { props: z.infer<S> }>): Entry {
  return { schema, description, Render: Render as Entry["Render"] };
}

export type Catalog = Record<string, Entry>;

const JUSTIFY = { start: "justify-start", center: "justify-center", end: "justify-end", spaceBetween: "justify-between" };
const TEXT = {
  h1: "text-xl font-semibold tracking-tight",
  h2: "text-lg font-semibold tracking-tight",
  h3: "text-sm font-semibold",
  body: "text-sm",
  caption: "text-xs text-muted-foreground",
};
const BUTTON = { primary: "default", secondary: "outline", destructive: "destructive" } as const;
const BADGE = ["default", "secondary", "outline", "destructive"] as const;
const usd = (n: number) => `$${n.toFixed(2)}`;
const htmlId = (n: Node) => `a2ui-${n.id}`;

export const viewCatalog: Catalog = {
  Card: entry(props({ child: Ref }), "bordered box", ({ props, child }) => (
    <Card className="gap-0 py-0">
      <CardContent className="flex flex-col gap-3 p-4">{child(props.child)}</CardContent>
    </Card>
  )),
  Column: entry(props({ children: Children }), "vertical stack", ({ children }) => <div className="flex flex-col gap-3">{children()}</div>),
  Row: entry(props({ children: Children, justify: z.enum(["start", "center", "end", "spaceBetween"]).optional() }), "horizontal stack", ({ props, children }) => (
    <div className={cn("flex flex-wrap items-center gap-2", JUSTIFY[props.justify ?? "start"])}>{children()}</div>
  )),
  List: entry(
    props({ children: Children, direction: z.enum(["vertical", "horizontal"]).optional() }),
    "repeat a template over an array in the data model; paths inside are relative to the item",
    ({ props, children }) => (
      <div className={props.direction === "horizontal" ? "grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3" : "flex flex-col gap-2"}>{children()}</div>
    ),
  ),
  Text: entry(props({ text: Dyn, variant: z.enum(["h1", "h2", "h3", "body", "caption"]).optional() }), "text", ({ props, text }) => (
    <p className={TEXT[props.variant ?? "body"]}>{text(props.text)}</p>
  )),
  Badge: entry(props({ text: Dyn, variant: z.enum(BADGE).optional() }), "small status label", ({ props, text }) => (
    <Badge variant={props.variant ?? "secondary"}>{text(props.text)}</Badge>
  )),
  KeyValue: entry(props({ label: Dyn, value: Dyn }), "one label/value line", ({ props, text }) => (
    <div className="flex items-baseline justify-between gap-4 text-sm">
      <span className="text-muted-foreground">{text(props.label)}</span>
      <span className="font-medium tabular-nums">{text(props.value)}</span>
    </div>
  )),
  Divider: entry(props({}), "separator line", () => <Separator />),
  InventoryTable: entry(props({ env: z.string().optional() }), "what exists, from the server's inventory (live)", ({ props }) => {
    const { inventory } = useContext(DomainData);
    if (!inventory) return <p className="text-xs text-muted-foreground">inventory unavailable</p>;
    const rows = inventory.resources.filter((r) => !props.env || r.env === props.env);
    if (!rows.length) return <p className="text-xs text-muted-foreground">nothing provisioned{props.env ? ` in ${props.env}` : ""}</p>;
    return (
      <Table className="text-xs">
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.name}>
              <TableCell>
                <Badge variant="outline">{r.env}</Badge>
              </TableCell>
              <TableCell className="text-muted-foreground">{r.kind}</TableCell>
              <TableCell>{r.name}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    );
  }),
  PlanCost: entry(props({}), "the current plan's resources and monthly cost, priced by the server (live)", () => {
    const { plan, cost } = useContext(DomainData).state;
    if (!plan || !cost) return <p className="text-xs text-muted-foreground">no priced plan yet</p>;
    return (
      <div className="flex flex-col gap-1 text-sm">
        {Object.entries(cost.lines).map(([name, n]) => (
          <div key={name} className="flex justify-between gap-4">
            <span className="text-muted-foreground">{name}</span>
            <span className="tabular-nums">{usd(n)}</span>
          </div>
        ))}
        <div className="flex justify-between gap-4 border-t pt-1 font-medium">
          <span>
            {plan.destroy ? "saves" : "total"} · {plan.env}
          </span>
          <span className="tabular-nums">{usd(cost.total)}/month</span>
        </div>
      </div>
    );
  }),
};

export const formCatalog: Catalog = {
  ...viewCatalog,
  TextField: entry(props({ label: Dyn, value: Bound, variant: z.enum(["shortText", "longText", "number"]).optional() }), "text input", ({ node, props, text, set, disabled }) => {
    const common = { id: htmlId(node), value: text(props.value), disabled, onChange: (e: { target: { value: string } }) => set(props.value.path, e.target.value) };
    return (
      <div className="grid gap-1.5">
        <Label htmlFor={htmlId(node)}>{text(props.label)}</Label>
        {props.variant === "longText" ? <Textarea rows={2} {...common} /> : <Input type={props.variant === "number" ? "number" : "text"} {...common} />}
      </div>
    );
  }),
  ChoicePicker: entry(
    props({ label: Dyn, options: z.array(z.object({ label: z.string(), value: z.string() })).max(100), value: Bound }),
    "pick one option",
    ({ node, props, text, set, disabled }) => (
      <div className="grid gap-1.5">
        <Label htmlFor={htmlId(node)}>{text(props.label)}</Label>
        <Select value={text(props.value) || undefined} onValueChange={(v) => set(props.value.path, v)} disabled={disabled}>
          <SelectTrigger id={htmlId(node)} className="w-full">
            <SelectValue placeholder="Choose…" />
          </SelectTrigger>
          <SelectContent>
            {props.options.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    ),
  ),
  CheckBox: entry(props({ label: Dyn, value: Bound }), "checkbox", ({ node, props, value, text, set, disabled }) => (
    <div className="flex items-center gap-2">
      <Checkbox id={htmlId(node)} checked={value(props.value) === true} onCheckedChange={(c) => set(props.value.path, c === true)} disabled={disabled} />
      <Label htmlFor={htmlId(node)}>{text(props.label)}</Label>
    </div>
  )),
  Button: entry(
    props({
      child: Ref,
      variant: z.enum(["primary", "secondary", "destructive"]).optional(),
      action: z.object({ event: z.object({ name: z.string(), context: z.record(z.string(), Dyn).optional() }) }),
    }),
    "sends an action to the agent",
    ({ node, props, child, fire, disabled }) => (
      <Button size="sm" variant={BUTTON[props.variant ?? "secondary"]} disabled={disabled} onClick={() => fire(node)}>
        {child(props.child)}
      </Button>
    ),
  ),
};

/** Shown instead of a type the catalog doesn't have: the agent can't invent components. */
export function Unsupported({ type }: { type: string }) {
  return <p className="rounded border border-dashed px-2 py-1 text-xs text-muted-foreground">unsupported component: {type}</p>;
}

/** Shown instead of a node whose props don't match its schema. */
export function Invalid({ type, issue }: { type: string; issue: string }) {
  return (
    <p className="rounded border border-dashed border-destructive/50 px-2 py-1 text-xs text-destructive">
      invalid {type}: {issue}
    </p>
  );
}

// What the client says it renders. The server only reads the catalogId from it and tells the agent its
// own a2ui.VIEW_CATALOG (the browser doesn't decide what an LLM may use); other servers may read the rest.
const SCHEMA = {
  catalogId: CATALOG_ID,
  components: Object.fromEntries(
    Object.entries(viewCatalog).map(([name, e]) => {
      const { properties, required } = z.toJSONSchema(e.schema.omit({ id: true, component: true })) as { properties?: object; required?: string[] };
      return [name, { description: e.description, properties, required }];
    }),
  ),
};

// The description must match ag-ui's A2UI_SCHEMA_CONTEXT_DESCRIPTION exactly: that is how
// ag-ui-langgraph recognises this entry and moves it to state["ag-ui"]["a2ui_schema"].
export const A2UI_CONTEXT: Context = {
  description:
    "A2UI Component Schema — available components for generating UI surfaces. Use these component names and properties when creating A2UI operations.",
  value: JSON.stringify(SCHEMA),
};
