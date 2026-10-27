// A2UI v0.9 on the client: operations -> surfaces, and JSON-pointer-style data paths.
// No React here; the renderer (A2UISurface.tsx) and the catalog (catalog.tsx) build on it.

export type Dynamic = string | number | boolean | { path: string };
export type Template = { componentId: string; path: string };
export type ActionDef = { event?: { name: string; context?: Record<string, Dynamic> } };

/** One component in the flat list. Children are referenced by id, never nested. */
export type Node = {
  id: string;
  component: string; // the catalog type: "Card", "TextField", ...
  child?: string;
  children?: string[] | Template;
  action?: ActionDef;
  [prop: string]: unknown;
};

export type Op = {
  version?: string;
  createSurface?: { surfaceId: string; catalogId: string };
  updateComponents?: { surfaceId: string; components: Node[] };
  updateDataModel?: { surfaceId: string; path?: string; value: unknown };
  deleteSurface?: { surfaceId: string };
};

export type Surface = { id: string; catalogId: string; components: Record<string, Node>; data: unknown };

/** The action a button sends back to the agent (A2UI v0.9 client -> server message). */
export type UserAction = {
  version: "v0.9";
  action: { name: string; surfaceId: string; sourceComponentId: string; timestamp: string; context: Record<string, unknown> };
};

export function applyOps(surfaces: Record<string, Surface>, ops: Op[]): Record<string, Surface> {
  const next = { ...surfaces };
  for (const op of ops) {
    if (op.createSurface) {
      const { surfaceId, catalogId } = op.createSurface;
      next[surfaceId] = { id: surfaceId, catalogId, components: {}, data: {} };
    } else if (op.updateComponents) {
      const s = next[op.updateComponents.surfaceId];
      if (!s) continue; // updates for a surface that was never created are ignored
      const components = { ...s.components };
      for (const c of op.updateComponents.components) if (c && typeof c.id === "string") components[c.id] = c;
      next[s.id] = { ...s, components };
    } else if (op.updateDataModel) {
      const s = next[op.updateDataModel.surfaceId];
      if (!s) continue;
      next[s.id] = { ...s, data: setPath(s.data, op.updateDataModel.path ?? "/", op.updateDataModel.value) };
    } else if (op.deleteSurface) {
      delete next[op.deleteSurface.surfaceId];
    }
  }
  return next;
}

/** A tool result or interrupt value carrying {"a2ui_operations": [...]} (the ag-ui convention). */
export function opsFrom(value: unknown): Op[] | null {
  let v = value;
  if (typeof v === "string") {
    try {
      v = JSON.parse(v);
    } catch {
      return null;
    }
  }
  const ops = (v as { a2ui_operations?: unknown } | null)?.a2ui_operations;
  return Array.isArray(ops) ? (ops as Op[]) : null;
}

const parts = (path: string) => path.split("/").filter(Boolean);

/** "/form/env" against the data model; relative paths ("name") resolve against `scope` (a List item). */
export function absolute(path: string, scope = ""): string {
  return path.startsWith("/") ? path : `${scope}/${path}`;
}

export function getPath(data: unknown, path: string): unknown {
  return parts(path).reduce<unknown>((v, k) => (v == null ? undefined : (v as Record<string, unknown>)[k]), data);
}

export function setPath(data: unknown, path: string, value: unknown): unknown {
  const [head, ...rest] = parts(path);
  if (head === undefined) return value;
  const base = (data && typeof data === "object" ? data : {}) as Record<string, unknown>;
  const copy: Record<string, unknown> = Array.isArray(base) ? ([...base] as unknown as Record<string, unknown>) : { ...base };
  copy[head] = setPath(base[head], "/" + rest.join("/"), value);
  return copy;
}
