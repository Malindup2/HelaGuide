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

export interface InvisibleEditResult {
  page: string;
  edit: string;
  before_content_hash: string;
  after_content_hash: string;
  before_structure_hash: string;
  after_structure_hash: string;
  layout_byte_identical: boolean;
  classification: string;
  detail: { simhash_distance?: number; char_delta?: number; magnitude?: string };
}

export interface TokenCostResult {
  pages_extracted_so_far: number;
  total_tokens_so_far: number;
  avg_tokens_per_page: number;
  live_unchanged_check_ms: number | null;
  live_unchanged_check_tokens: number;
  live_classification: string | null;
}

export interface QuoteGroundingResult {
  checked: number;
  passed: number;
  results: { fact_id: string; value: string; url: string; quote: string; found_on_page: boolean }[];
}

export interface OrderedWorkflowResult {
  question: string;
  graph_ordered_steps: string[];
  baseline_unordered_matches: string[];
}

export interface TraversalScalingResult {
  ancestor_set_size: number;
  rows: { nodes: number; scoped_ms: number; whole_graph_ms: number }[];
  scoped_growth_x: number;
  whole_graph_growth_x: number;
}

export type BenchmarkKey =
  | "crawler_ablation"
  | "so1_classification"
  | "so3_staleness"
  | "so5_workflow"
  | "b3_traversal";

export interface BenchmarkResult {
  which: BenchmarkKey;
  script: string;
  command: string;
  returncode: number;
  elapsed_ms: number;
  stdout: string;
  stderr: string;
}

export interface CrawlRun {
  run_id: string;
  started_at: string | null;
  finished_at: string | null;
  mode: string;
  pages: number | null;
  counts: Record<string, number> | null;
  to_extract: number | null;
}

export interface CrawlPageResult {
  url: string;
  change_class: string;
  http_status: number | null;
  duration_ms: number | null;
  char_count: number | null;
  fetched_at: string | null;
  run_id: string;
}

export interface CrawlExtraction {
  source_url: string;
  model: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  facts: number;
  dropped: number;
  error: string | null;
  created_at: string | null;
}

export interface CrawlActivity {
  runs: CrawlRun[];
  pages: CrawlPageResult[];
  extractions: CrawlExtraction[];
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
  // Live novelty demonstrations -- each one runs the real production code against the
  // real saved pages and the real database, right now. Nothing here is a cached number.
  demoInvisibleEdit: () =>
    call<InvisibleEditResult>("/api/demo/invisible_edit", { method: "POST" }),
  demoTokenCost: () => call<TokenCostResult>("/api/demo/token_cost"),
  demoQuoteGrounding: (n = 10) =>
    call<QuoteGroundingResult>(`/api/demo/quote_grounding?n=${n}`),
  demoOrderedWorkflow: (service = "svc:passport") =>
    call<OrderedWorkflowResult>(`/api/demo/ordered_workflow?service=${encodeURIComponent(service)}`),
  demoTraversalScaling: () => call<TraversalScalingResult>("/api/demo/traversal_scaling"),
  // Runs the EXACT script named in the proposal's own ablation plan (research/experiments/*.py)
  // as a subprocess and returns its real stdout -- the same output an examiner would see
  // running it from the command line, not a re-implementation.
  runBenchmark: (which: BenchmarkKey) =>
    call<BenchmarkResult>(`/api/benchmark/${which}`, { method: "POST" }),
  // Real crawl history: which URLs were fetched, how long each took, and what each LLM
  // extraction call cost in tokens -- read from Postgres, not a live feed (acquisition
  // runs as a one-shot batch script, not a server).
  crawlActivity: (limit = 50) => call<CrawlActivity>(`/api/crawl/activity?limit=${limit}`),
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
