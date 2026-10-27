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
      // A2UI (and ag-ui's toolkit) use path "/" for the whole model; in RFC 6901 "/" would be the key ""
      const path = op.updateDataModel.path ?? "/";
      next[s.id] = { ...s, data: setPath(s.data, path === "/" ? "" : path, op.updateDataModel.value) };
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

// JSON Pointers (RFC 6901), as A2UI v0.9 specifies. Paths come from an LLM, so nothing here throws:
// a bad pointer reads as undefined and a bad write is dropped (a throw inside render would take
// the whole chat down).

const INDEX = /^(0|[1-9][0-9]*)$/;

/** "" is the whole document; "/a/b" -> ["a", "b"]; "~1" is "/" and "~0" is "~" inside a token. */
function tokens(pointer: string): string[] | null {
  if (pointer === "") return [];
  if (!pointer.startsWith("/")) return null;
  return pointer.slice(1).split("/").map((t) => t.replace(/~1/g, "/").replace(/~0/g, "~"));
}

/** "/form/env" against the data model; relative paths ("name") resolve against `scope` (a List item). */
export function absolute(path: string, scope = ""): string {
  return path.startsWith("/") || path === "" ? path || scope : `${scope}/${path}`;
}

export function getPath(data: unknown, pointer: string): unknown {
  const ts = tokens(pointer);
  if (!ts) return undefined;
  let cur: unknown = data;
  for (const t of ts) {
    if (cur === null || typeof cur !== "object") return undefined;
    if (Array.isArray(cur)) {
      if (!INDEX.test(t)) return undefined; // the spec: a non-numeric index on an array is an error
      cur = cur[Number(t)];
    } else {
      cur = (cur as Record<string, unknown>)[t];
    }
  }
  return cur;
}

export function setPath(data: unknown, pointer: string, value: unknown): unknown {
  const ts = tokens(pointer);
  if (!ts) return data;
  const write = (node: unknown, i: number): unknown => {
    if (i === ts.length) return value;
    const t = ts[i];
    if (Array.isArray(node)) {
      if (!INDEX.test(t)) throw new RangeError(t); // caught below: the whole write is dropped
      const copy = [...node];
      copy[Number(t)] = write(node[Number(t)], i + 1);
      return copy;
    }
    const base = node && typeof node === "object" ? (node as Record<string, unknown>) : {};
    return { ...base, [t]: write(base[t], i + 1) };
  };
  try {
    return write(data, 0);
  } catch {
    return data;
  }
}
