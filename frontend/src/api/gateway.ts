// The frontend talks to the gateway only, never to a component directly.
import type { Render } from "./types";

const BASE = import.meta.env.VITE_GATEWAY_URL ?? "http://localhost:8000";

export async function askForGuidance(sessionId: string, text: string): Promise<Render> {
  const res = await fetch(`${BASE}/v1/guidance`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, text }),
  });
  if (!res.ok) throw new Error(`gateway ${res.status}: ${await res.text()}`);
  return res.json();
}
