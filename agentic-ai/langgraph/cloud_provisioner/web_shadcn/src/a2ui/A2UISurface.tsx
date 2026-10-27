// Draws one A2UI surface with the catalog. The renderer knows the protocol (ids, children,
// data binding, actions); the catalog knows the look (shadcn). Neither knows about the agent.
//
//   node.component ──► catalog[type] ──► shadcn component       unknown type ──► <Unsupported/>
//   { path: "/form/env" } ──► value() reads, set() writes the surface's local data model
//   Button action ──► fire() resolves the context paths ──► onAction(UserAction)

import { useState, type ReactNode } from "react";
import { catalog, Unsupported, type RenderCtx } from "./catalog";
import { absolute, getPath, setPath, type Dynamic, type Node, type Surface, type UserAction } from "./surface";

const MAX_DEPTH = 24; // the component list comes from an LLM: never trust it to be a tree

export function A2UISurface({ surface, onAction, disabled }: { surface: Surface; onAction: (a: UserAction) => void; disabled?: boolean }) {
  const [data, setData] = useState(surface.data); // inputs write here; the agent sees it only via an action

  function render(id: string, scope: string, depth: number): ReactNode {
    const node = surface.components[id];
    if (!node || depth > MAX_DEPTH) return null;
    const Component = catalog[node.component];
    if (!Component) return <Unsupported key={`${scope}:${id}`} type={node.component} />;

    const value = (v: unknown) =>
      v && typeof v === "object" && "path" in v ? getPath(data, absolute((v as { path: string }).path, scope)) : v;

    const ctx: RenderCtx = {
      node,
      disabled: !!disabled,
      value,
      text: (v) => {
        const r = value(v);
        return r == null ? "" : String(r);
      },
      set: (path, v) => setData((d: unknown) => setPath(d, absolute(path, scope), v)),
      child: (childId) => (childId ? render(childId, scope, depth + 1) : null),
      children: () => {
        const c = node.children;
        if (Array.isArray(c)) return c.map((cid) => render(cid, scope, depth + 1));
        if (c && typeof c === "object") {
          // a List template: render componentId once per item, paths inside are relative to the item
          const base = absolute(c.path, scope);
          const items = getPath(data, base);
          return Array.isArray(items) ? items.map((_, i) => render(c.componentId, `${base}/${i}`, depth + 1)) : null;
        }
        return null;
      },
      fire: (n: Node) => {
        const event = n.action?.event;
        if (!event || disabled) return;
        const context: Record<string, unknown> = {};
        for (const [k, v] of Object.entries(event.context ?? {})) context[k] = value(v as Dynamic);
        onAction({
          version: "v0.9",
          action: { name: event.name, surfaceId: surface.id, sourceComponentId: n.id, timestamp: new Date().toISOString(), context },
        });
      },
    };
    return <Component key={`${scope}:${id}`} {...ctx} />;
  }

  return <div className="a2ui-surface">{render("root", "", 0)}</div>;
}
