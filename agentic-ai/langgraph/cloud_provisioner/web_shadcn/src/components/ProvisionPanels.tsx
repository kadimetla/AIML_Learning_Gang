// Hand-built panels, fed by STATE_SNAPSHOT and the approval interrupt. Deliberately NOT A2UI:
// the plan a human approves is drawn by code from validated, priced state.

import { useEffect, useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

export type Action = { op: string; name: string; kind: string; status: string; attempts: number; cloud_id: string | null; error: string | null };
export type ProvisionState = {
  phase?: string;
  plan?: { env: string; region: string; destroy: boolean; budget_usd?: number | null } | null;
  cost?: { lines: Record<string, number>; total: number } | null;
  issues?: string[];
  actions?: Action[];
};
export type Row = { name: string; kind: string; env: string; region: string; cloud_id: string };

const ICON: Record<string, string> = { ready: "✓", deleted: "✓", retrying: "↻", failed: "✗", pending: "·" };
const PHASE: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  awaiting_approval: "default",
  applying: "default",
  done: "secondary",
  failed: "destructive",
  policy_failed: "destructive",
  over_budget: "destructive",
};

export function ApprovalCard({ message, destroy, expiresAt, onDecide }: { message: string; destroy: boolean; expiresAt?: string; onDecide: (approved: boolean, reason: string) => void }) {
  const [reason, setReason] = useState("");
  // the server enforces the deadline (approve() refuses a late "yes"); this only tells the human
  const until = expiresAt ? new Date(expiresAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : null;
  return (
    <Alert variant={destroy ? "destructive" : "default"} className="border-2">
      <AlertTitle>⏸ Approval needed</AlertTitle>
      <AlertDescription className="flex flex-col gap-3">
        <p className="text-foreground">{message}</p>
        <p>
          The graph is paused in approve(). Nothing changes until you decide.
          {until && ` Valid until ${until}; policy is checked again when you approve.`}
        </p>
        <Input placeholder="reason (if rejecting)" value={reason} onChange={(e) => setReason(e.target.value)} />
        <div className="flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={() => onDecide(false, reason)}>
            Reject
          </Button>
          <Button variant={destroy ? "destructive" : "default"} size="sm" onClick={() => onDecide(true, "")}>
            Approve
          </Button>
        </div>
      </AlertDescription>
    </Alert>
  );
}

export function PlanPanel({ state, running }: { state: ProvisionState; running: boolean }) {
  const { plan, cost, issues = [], actions = [], phase } = state;
  const next = running && phase === "applying" ? actions.find((a) => a.status === "pending" || a.status === "retrying") : undefined;
  return (
    <Card className="gap-3">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-sm">
          {plan?.destroy ? "Destroy" : "Plan"}
          {plan ? ` · ${plan.env} · ${plan.region}` : ""}
        </CardTitle>
        {phase && <Badge variant={PHASE[phase] ?? "outline"}>{phase}</Badge>}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {!plan && !issues.length && <p className="text-sm text-muted-foreground">No plan yet. Describe what you need in the chat.</p>}
        {issues.length > 0 && (
          <ul className="list-disc space-y-1 rounded-md bg-destructive/10 py-2 pr-2 pl-6 text-xs text-destructive">
            {issues.map((i) => (
              <li key={i}>{i}</li>
            ))}
          </ul>
        )}
        {actions.length > 0 && (
          <Table className="text-xs">
            <TableBody>
              {actions.map((a) => (
                <TableRow key={a.name} className={cn(a.status === "failed" && "text-destructive")}>
                  <TableCell className="w-4">{a === next ? "…" : ICON[a.status] ?? "·"}</TableCell>
                  <TableCell className="text-muted-foreground">{a.kind}</TableCell>
                  <TableCell>
                    {a.name}
                    {a.error && <div className="text-[11px] text-muted-foreground">{a.error.slice(0, 80)}</div>}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{cost ? `$${(cost.lines[a.name] ?? 0).toFixed(2)}` : ""}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {cost && (
          <p className="text-right text-sm">
            {plan?.destroy ? "saves" : "total"} <b className="tabular-nums">${cost.total.toFixed(2)}</b>/month
            {plan?.budget_usd ? <span className="text-muted-foreground"> · budget ${plan.budget_usd}</span> : null}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export type InventoryData = { provider: string; resources: Row[] };

/** GET /inventory (the server's record of what exists), again whenever refreshKey changes. */
export function useInventory(refreshKey: number): InventoryData | null {
  const [data, setData] = useState<InventoryData | null>(null);
  useEffect(() => {
    fetch("/inventory")
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData(null));
  }, [refreshKey]);
  return data;
}

export function Inventory({ data }: { data: InventoryData | null }) {
  return (
    <Card className="gap-3">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-sm">Inventory</CardTitle>
        <span className="text-xs text-muted-foreground">{data ? `${data.provider} cloud` : "server offline"}</span>
      </CardHeader>
      <CardContent>
        {data && data.resources.length === 0 && <p className="text-sm text-muted-foreground">nothing provisioned</p>}
        {data && data.resources.length > 0 && (
          <Table className="text-xs">
            <TableBody>
              {data.resources.map((r) => (
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
        )}
      </CardContent>
    </Card>
  );
}
