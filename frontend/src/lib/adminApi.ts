/** Thin fetch wrapper for the real C2 backend (components/c2-knowledge-graph/service,
 * `python -m app.admin_ui`, proxied at /c2-api by vite.config.ts). No mock data here --
 * every call hits the live Postgres + Neo4j state. */

const BASE = "/c2-api";

export interface FileRow {
  state: "read" | "to_read" | "changed" | "nothing" | "older";
  latest: boolean;
  url: string;
  agency: string | null;
  signals: string;
  gate_send: boolean;
}

export interface GraphSummary {
  services: number;
  agencies: number;
  documents: number;
  "facts (current)": number;
  "facts (all versions)": number;
  "REQUIRES edges": number;
}

export interface GraphData {
  summary: GraphSummary;
  chain: { a: string; b: string }[];
  empty_services: string[];
}

export interface PendingFact {
  id: number;
  fact_id: string;
  service: string;
  predicate: string;
  value: string;
  unit: string | null;
  old: string | null;
  quote: string;
  url: string;
  new_service: boolean;
}

export interface Status {
  postgres: boolean;
  neo4j: boolean;
  model_key: boolean;
}

async function call<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${path}: ${body.slice(0, 200)}`);
  }
  return res.json();
}

export const adminApi = {
  status: () => call<Status>("/api/status"),
  files: () => call<FileRow[]>("/api/files"),
  graph: () => call<GraphData>("/api/graph"),
  pending: (service?: string) =>
    call<PendingFact[]>(`/api/pending${service ? `?service=${encodeURIComponent(service)}` : ""}`),
  decide: (ids: number[], decision: "approved" | "rejected", reason: string, reviewer = "malindu") =>
    call<{ decided: number; skipped: number }>("/api/decide", {
      method: "POST",
      body: JSON.stringify({ ids, decision, reason, reviewer }),
    }),
  write: () =>
    call<{ new: number; changed: number; same: number; failed: unknown[]; graph: GraphSummary }>(
      "/api/write",
      { method: "POST" },
    ),
};

const DEPARTMENTS = [
  { key: "drp", label: "DRP (NIC)", match: "drp.gov.lk" },
  { key: "immigration", label: "Immigration", match: "immigration.gov.lk" },
  { key: "rgd", label: "RGD", match: "rgd.gov.lk" },
  { key: "ird", label: "Inland Revenue", match: "ird.gov.lk" },
] as const;

export type DepartmentKey = (typeof DEPARTMENTS)[number]["key"];

export function departmentOf(url: string) {
  return DEPARTMENTS.find((d) => url.includes(d.match)) ?? null;
}

export { DEPARTMENTS };
