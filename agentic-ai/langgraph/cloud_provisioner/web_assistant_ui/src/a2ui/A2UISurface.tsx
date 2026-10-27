// Draws one A2UI surface with a catalog. The renderer knows the protocol (ids, children,
// data binding, actions); the catalog knows the look (shadcn). Neither knows about the agent.
//
//   node.component ──► catalog[type] ──► schema check ──► shadcn component
//                      unknown type ──► <Unsupported/>      bad props ──► <Invalid/>
//   { path: "/form/env" } ──► value() reads, set() writes the surface's local data model
//   Button action ──► fire() resolves the context paths ──► onAction(UserAction)
//
// The caller picks the catalog: viewCatalog for LLM-made views, formCatalog for code-built forms.

import { useState, type ReactNode } from "react";
import { Invalid, Unsupported, type Catalog, type RenderCtx } from "./catalog";
import { absolute, getPath, setPath, type Dynamic, type Node, type Surface, type UserAction } from "./surface";

const MAX_DEPTH = 24; // the component list comes from an LLM: never trust it to be a tree

type Props = { surface: Surface; catalog: Catalog; onAction?: (a: UserAction) => void; disabled?: boolean };

export function A2UISurface({ surface, catalog, onAction, disabled }: Props) {
  const [data, setData] = useState(surface.data); // inputs write here; the agent sees it only via an action
  // a new data model from the agent (updateDataModel on this surface) replaces local edits;
  // React's "adjust state when a prop changes" pattern, so there's no stale frame
  const [seen, setSeen] = useState(surface.data);
  if (seen !== surface.data) {
    setSeen(surface.data);
    setData(surface.data);
  }

  function render(id: string, scope: string, depth: number): ReactNode {
    const node = surface.components[id];
    if (!node || depth > MAX_DEPTH) return null;
    const key = `${scope}:${id}`;
    const entry = Object.hasOwn(catalog, node.component) ? catalog[node.component] : undefined;
    if (!entry) return <Unsupported key={key} type={String(node.component)} />;
    const checked = entry.schema.safeParse(node);
    if (!checked.success) {
      const issue = checked.error.issues[0];
      return <Invalid key={key} type={node.component} issue={`${issue.path.join(".") || "props"}: ${issue.message}`} />;
    }

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
        if (!event || disabled || !onAction) return;
        const context: Record<string, unknown> = {};
        for (const [k, v] of Object.entries(event.context ?? {})) context[k] = value(v as Dynamic);
        onAction({
          version: "v0.9",
          action: { name: event.name, surfaceId: surface.id, sourceComponentId: n.id, timestamp: new Date().toISOString(), context },
        });
      },
    };
    const { Render } = entry;
    return <Render key={key} {...ctx} props={checked.data as never} />;
  }

  return <div className="a2ui-surface">{render("root", "", 0)}</div>;
}
