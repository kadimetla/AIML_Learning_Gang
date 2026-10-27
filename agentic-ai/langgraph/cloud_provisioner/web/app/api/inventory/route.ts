// Read-only proxy to the Python server's inventory, so the browser needs no CORS setup.

const SERVER_URL = (process.env.AGENT_URL ?? "http://127.0.0.1:8001/agent").replace(/\/agent$/, "");

export async function GET() {
  const res = await fetch(`${SERVER_URL}/inventory`, { cache: "no-store" });
  return new Response(res.body, { status: res.status, headers: { "content-type": "application/json" } });
}
