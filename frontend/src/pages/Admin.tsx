import { useEffect, useMemo, useState, useCallback, useRef } from "react";
import { Link } from "react-router-dom";
import {
  Database, GitBranch, FileText, CheckCircle2, XCircle, RefreshCw,
  AlertTriangle, Clock, Link2, Loader2, ChevronDown, ChevronRight,
  ArrowLeft, ExternalLink, Search, CheckSquare, Square,
  Sparkles,
} from "lucide-react";
import BrandMark from "../components/BrandMark";
import LanguageSwitch from "../components/LanguageSwitch";
import {
  adminApi, departmentOf, DEPARTMENTS,
  type FileRow, type GraphData, type PendingFact, type Status,
} from "../lib/adminApi";

type Key = "status" | "files" | "graph" | "pending";
type Tab = "overview" | "review" | "pages";

export default function Admin() {
  const [status, setStatus] = useState<Status | null>(null);
  const [files, setFiles] = useState<FileRow[] | null>(null);
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [pending, setPending] = useState<PendingFact[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [selected, setSelected] = useState<Set<number>>(() => new Set());
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const inFlight = useRef<Set<Key>>(new Set());
  const load = useCallback(async (which: Key[] = ["status", "pending"]) => {
    const jobs: Record<Key, () => Promise<void>> = {
      status: () => adminApi.status().then(setStatus),
      files: () => adminApi.files().then(setFiles),
      graph: () => adminApi.graph().then(setGraph),
      pending: () => adminApi.pending().then(setPending),
    };
    const todo = which.filter((k) => !inFlight.current.has(k));
    todo.forEach((k) => inFlight.current.add(k));
    try {
      await Promise.all(todo.map((k) => jobs[k]()));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      todo.forEach((k) => inFlight.current.delete(k));
    }
  }, []);

  useEffect(() => {
    load(["status", "pending"]);
  }, [load]);

  useEffect(() => {
    if (tab === "overview" && !graph) load(["files", "graph"]);
    if (tab === "pages" && !files) load(["files"]);
  }, [tab, graph, files, load]);

  const byDept = useMemo(() => {
    if (!files) return null;
    const out = Object.fromEntries(
      DEPARTMENTS.map((d) => [d.key, { total: 0, read: 0, skipped: 0 }])
    );
    for (const f of files) {
      if (!f.latest) continue;
      const dep = departmentOf(f.url);
      if (!dep) continue;
      if (!f.gate_send && f.state !== "read") {
        out[dep.key].skipped += 1;
        continue;
      }
      out[dep.key].total += 1;
      if (f.state === "read") out[dep.key].read += 1;
    }
    return out;
  }, [files]);

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll(ids: number[]) {
    setSelected((prev) => {
      const allSelected = ids.every((id) => prev.has(id));
      const next = new Set(prev);
      if (allSelected) {
        ids.forEach((id) => next.delete(id));
      } else {
        ids.forEach((id) => next.add(id));
      }
      return next;
    });
  }

  async function decide(decision: "approved" | "rejected") {
    if (selected.size === 0) return;
    if (decision === "rejected") {
      const reason = window.prompt("Reason for rejecting (required):", "");
      if (!reason || !reason.trim()) return;
      setBusy(true);
      try {
        const r = await adminApi.decide([...selected], "rejected", reason.trim());
        setToast(`Rejected ${r.decided} candidate fact(s).`);
        setSelected(new Set());
        await load(["pending"]);
      } catch (e) {
        setToast(`Failed: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        setBusy(false);
      }
      return;
    }
    setBusy(true);
    try {
      const r = await adminApi.decide([...selected], "approved", "reviewed in admin console");
      setToast(`Approved ${r.decided} fact(s) for graph integration.`);
      setSelected(new Set());
      await load(["pending"]);
    } catch (e) {
      setToast(`Failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  async function writeToGraph() {
    setBusy(true);
    try {
      const r = await adminApi.write();
      setToast(
        `Wrote ${r.new} new, ${r.changed} updated, ${r.failed?.length ?? 0} failed to Neo4j graph.`
      );
      await load(["pending", "graph"]);
    } catch (e) {
      setToast(`Failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  const loading =
    tab === "overview"
      ? !status || !files || !graph
      : tab === "pages"
      ? !status || !files
      : !status || !pending;

  return (
    <div className="min-h-screen bg-paper text-ink font-sans selection:bg-amber-500 selection:text-navy-950">
      {/* ── Topbar & Header ── */}
      <header className="sticky top-0 z-50 shadow-sm transition-colors">
        {/* Government Top Bar */}
        <div className="bg-navy-950 text-slate-300 border-b border-white/10 py-1.5 px-4 text-xs">
          <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="inline-flex items-center gap-1.5 bg-amber-500 text-navy-950 font-bold px-2.5 py-0.5 rounded-full text-[11px] tracking-wide shadow-xs">
                C2 OPS
              </span>
              <span className="hidden sm:inline-flex items-center gap-2 text-slate-300 font-medium text-[11px]">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                C2 KNOWLEDGE GRAPH ORCHESTRATOR · SLIIT IT4010
              </span>
            </div>

            <div className="flex items-center gap-3">
              <LanguageSwitch />
            </div>
          </div>
        </div>

        {/* Main Nav */}
        <nav className="bg-paper/98 backdrop-blur-md border-b border-line py-3.5 px-4 sm:px-6 lg:px-8 w-full" aria-label="Admin Navigation">
          <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <Link
                to="/"
                className="inline-flex items-center gap-1.5 text-xs font-bold text-ink-2 hover:text-amber-600 bg-paper-2 hover:bg-paper-3 border border-line px-3 py-1.5 rounded-xl transition-all no-underline"
              >
                <ArrowLeft size={13} />
                <span>Citizen Portal</span>
              </Link>

              <div className="h-5 w-px bg-line" aria-hidden="true" />

              <div className="flex items-center gap-3">
                <BrandMark size={34} />
                <div>
                  <h1 className="text-base font-extrabold tracking-tight text-ink leading-none flex items-center gap-2">
                    Knowledge Graph Console
                    <span className="text-[10px] font-extrabold text-amber-600 bg-amber-500/15 border border-amber-500/25 px-1.5 py-0.5 rounded">
                      C2 Live
                    </span>
                  </h1>
                  <p className="text-[11px] text-ink-3 mt-0.5 font-medium">
                    Autonomous Crawl · Extraction · Human Review Gate · Neo4j
                  </p>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <StatusPill status={status} />

              <button
                type="button"
                onClick={() =>
                  load(
                    tab === "overview"
                      ? ["status", "files", "graph"]
                      : tab === "pages"
                      ? ["status", "files"]
                      : ["status", "pending"]
                  )
                }
                className="inline-flex items-center gap-1.5 rounded-xl border border-line bg-paper hover:bg-paper-2 px-3 py-1.5 text-xs font-bold text-ink-2 hover:text-ink transition-all cursor-pointer shadow-2xs"
              >
                <RefreshCw size={13} className={busy ? "animate-spin text-amber-500" : ""} />
                <span>Refresh</span>
              </button>
            </div>
          </div>

          {/* Sub Navigation Tabs */}
          <div className="max-w-7xl mx-auto flex gap-2 pt-4 border-t border-line/60 mt-3">
            {[
              { id: "overview", label: "Graph Overview", icon: Database },
              {
                id: "review",
                label: "Review Gate",
                icon: GitBranch,
                count: pending?.length,
              },
              { id: "pages", label: "Crawled Sources", icon: FileText, count: files?.length },
            ].map(({ id, label, icon: Icon, count }) => {
              const active = tab === id;
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => setTab(id as Tab)}
                  className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-bold transition-all cursor-pointer border-none ${
                    active
                      ? "bg-amber-500 text-navy-950 shadow-sm"
                      : "bg-paper-2 text-ink-2 hover:bg-paper-3 hover:text-ink"
                  }`}
                >
                  <Icon size={14} />
                  <span>{label}</span>
                  {typeof count === "number" && count > 0 && (
                    <span
                      className={`text-[10px] px-1.5 py-0.2 rounded-full font-bold ${
                        active
                          ? "bg-navy-950 text-amber-300"
                          : "bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30"
                      }`}
                    >
                      {count}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </nav>
      </header>

      {/* ── Main Content Body ── */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Backend Connectivity Notice */}
        {error && (
          <div className="mb-6 rounded-2xl border border-amber-300 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-950/20 p-5 text-sm text-amber-900 dark:text-amber-200 shadow-sm">
            <div className="flex items-start gap-3">
              <AlertTriangle size={18} className="mt-0.5 text-amber-600 shrink-0" />
              <div className="space-y-1">
                <div className="font-bold">C2 Orchestrator Backend Offline / Unreachable</div>
                <div className="text-xs opacity-90 leading-relaxed">{error}</div>
                <div className="mt-2 text-xs text-amber-800 dark:text-amber-300 bg-amber-500/10 p-2.5 rounded-xl border border-amber-500/20 font-mono">
                  To launch live C2 review server:{" "}
                  <span className="font-bold">python -m app.admin_ui</span> inside{" "}
                  <span className="font-bold">components/c2-knowledge-graph/service</span> (port 8765)
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Loading Indicator */}
        {loading && !error && (
          <div className="flex flex-col items-center justify-center py-20 text-ink-2 space-y-3">
            <Loader2 size={28} className="animate-spin text-amber-500" />
            <p className="text-sm font-semibold">Synchronizing live C2 knowledge graph telemetry...</p>
          </div>
        )}

        {/* Tab Views */}
        {!loading && tab === "overview" && <Overview graph={graph} byDept={byDept} />}
        {!loading && tab === "review" && (
          <ReviewQueue
            pending={pending}
            selected={selected}
            onToggle={toggle}
            onToggleAll={toggleAll}
            onDecide={decide}
            onWrite={writeToGraph}
            busy={busy}
          />
        )}
        {!loading && tab === "pages" && <Pages files={files} />}
      </main>

      {/* ── Toast Notification ── */}
      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 rounded-2xl border border-line bg-navy-900 text-white px-5 py-3 text-xs sm:text-sm font-semibold shadow-2xl flex items-center gap-3 z-50 animate-fadeIn">
          <Sparkles size={16} className="text-amber-400 shrink-0" />
          <span>{toast}</span>
          <button
            type="button"
            onClick={() => setToast(null)}
            className="text-white/60 hover:text-white ml-2 text-base font-bold cursor-pointer border-none bg-transparent"
          >
            &times;
          </button>
        </div>
      )}
    </div>
  );
}

function StatusPill({ status }: { status: Status | null }) {
  if (!status) return null;
  const ok = status.postgres && status.neo4j;
  return (
    <div
      className={`inline-flex items-center gap-2 rounded-xl px-3 py-1.5 text-xs font-bold border shadow-2xs ${
        ok
          ? "bg-emerald-500/10 border-emerald-500/25 text-emerald-600 dark:text-emerald-400"
          : "bg-amber-500/10 border-amber-500/25 text-amber-600 dark:text-amber-400"
      }`}
    >
      <span className={`w-2 h-2 rounded-full ${ok ? "bg-emerald-500 animate-pulse" : "bg-amber-500"}`} />
      <span>{ok ? "Postgres & Neo4j Active" : "Partial Connection"}</span>
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  highlight = false,
}: {
  icon: typeof Database;
  label: string;
  value: number | string;
  sub?: string;
  highlight?: boolean;
}) {
  return (
    <div className={`rounded-2xl border p-5 transition-all hover:-translate-y-1 hover:shadow-md ${
      highlight
        ? "border-amber-400/60 bg-gradient-to-br from-amber-500/10 to-transparent"
        : "border-line bg-paper-2 hover:border-amber-400/40"
    }`}>
      <div className="flex items-center justify-between gap-2 text-ink-3 mb-3">
        <span className="text-[11px] font-extrabold uppercase tracking-wider">{label}</span>
        <div className="w-8 h-8 rounded-xl grid place-items-center bg-paper text-amber-600 border border-line shadow-2xs">
          <Icon size={16} />
        </div>
      </div>
      <div className="text-3xl font-black text-ink tracking-tight font-mono">{value}</div>
      {sub && <div className="mt-1 text-xs text-ink-2 font-medium">{sub}</div>}
    </div>
  );
}

function Overview({
  graph,
  byDept,
}: {
  graph: GraphData | null;
  byDept: Record<string, { total: number; read: number; skipped: number }> | null;
}) {
  const g = graph?.summary;
  return (
    <div className="space-y-10">
      {/* ── Section: Knowledge Graph Metrics ── */}
      <section>
        <div className="flex items-center gap-2 mb-4">
          <span className="w-2 h-2 rounded-full bg-amber-500" />
          <h2 className="text-base font-extrabold tracking-tight text-ink uppercase">
            Graph Knowledge Topology
          </h2>
        </div>

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          <StatCard icon={Database} label="Services" value={g?.services ?? "—"} sub="Target workflows" highlight />
          <StatCard icon={Link2} label="Agencies" value={g?.agencies ?? "—"} sub="Gov authorities" />
          <StatCard icon={FileText} label="Documents" value={g?.documents ?? "—"} sub="Required forms & IDs" />
          <StatCard icon={CheckCircle2} label="Active Facts" value={g?.["facts (current)"] ?? "—"} sub="Extracted & verified" highlight />
          <StatCard icon={Clock} label="Fact Versions" value={g?.["facts (all versions)"] ?? "—"} sub="Temporal crawl history" />
          <StatCard icon={GitBranch} label="Prereq Edges" value={g?.["REQUIRES edges"] ?? "—"} sub="Inter-agency dependencies" highlight />
        </div>
      </section>

      {/* ── Section: Department Extraction Coverage ── */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-amber-500" />
            <h2 className="text-base font-extrabold tracking-tight text-ink uppercase">
              Department Coverage & Extraction Progress
            </h2>
          </div>
          <span className="text-xs text-ink-3 font-medium">Auto-updated via gate_send signal detection</span>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {DEPARTMENTS.map((d) => {
            const c = byDept?.[d.key] ?? { total: 0, read: 0, skipped: 0 };
            const pct = c.total ? Math.round((c.read / c.total) * 100) : 0;
            const waiting = c.total - c.read;
            return (
              <div
                key={d.key}
                className="rounded-2xl border border-line bg-paper-2 p-5 hover:border-amber-400/50 hover:shadow-sm transition-all"
              >
                <div className="flex items-center justify-between gap-2 mb-2">
                  <h3 className="text-sm font-bold text-ink leading-snug">{d.label}</h3>
                  <span className="text-xs font-mono font-bold text-amber-600 bg-amber-500/10 px-2 py-0.5 rounded-md shrink-0">
                    {pct}%
                  </span>
                </div>

                <div className="flex items-baseline gap-1.5 text-xs text-ink-2 mb-3">
                  <span className="text-xl font-black text-ink font-mono">{c.read}</span>
                  <span>/ {c.total} pages with extracted facts</span>
                </div>

                {/* Progress Bar */}
                <div className="h-2 w-full overflow-hidden rounded-full bg-paper border border-line">
                  <div
                    className="h-full bg-gradient-to-r from-amber-500 to-amber-400 rounded-full transition-all duration-500"
                    style={{ width: `${pct}%` }}
                  />
                </div>

                <div className="mt-3 pt-3 border-t border-line/60 flex items-center justify-between text-[11px]">
                  {waiting > 0 ? (
                    <span className="text-amber-700 dark:text-amber-400 font-semibold">
                      {waiting} awaiting extraction
                    </span>
                  ) : (
                    <span className="text-emerald-600 dark:text-emerald-400 font-semibold flex items-center gap-1">
                      <CheckCircle2 size={12} /> All parsed
                    </span>
                  )}
                  <span className="text-ink-3">{c.skipped} noise skipped</span>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* ── Section: Empty Services Alert ── */}
      {graph && graph.empty_services.length > 0 && (
        <section className="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-6">
          <div className="flex items-center gap-2 text-sm font-bold text-amber-800 dark:text-amber-300 mb-2">
            <AlertTriangle size={16} className="text-amber-500" />
            <span>Services with No Extracted Facts ({graph.empty_services.length})</span>
          </div>
          <p className="text-xs text-ink-2 mb-4">
            These services are registered in the ontology catalog but currently have no confirmed facts extracted from departmental crawls:
          </p>
          <div className="flex flex-wrap gap-2">
            {graph.empty_services.map((id) => (
              <span
                key={id}
                className="rounded-lg border border-line bg-paper px-3 py-1 font-mono text-xs text-ink-2 shadow-2xs"
              >
                {id}
              </span>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function ReviewQueue({
  pending,
  selected,
  onToggle,
  onToggleAll,
  onDecide,
  onWrite,
  busy,
}: {
  pending: PendingFact[] | null;
  selected: Set<number>;
  onToggle: (id: number) => void;
  onToggleAll: (ids: number[]) => void;
  onDecide: (d: "approved" | "rejected") => void;
  onWrite: () => void;
  busy: boolean;
}) {
  const [open, setOpen] = useState<Set<string>>(() => new Set());

  if (!pending?.length) {
    return (
      <div className="rounded-2xl border border-line bg-paper-2 p-12 text-center space-y-4">
        <div className="w-16 h-16 rounded-full bg-emerald-500/10 text-emerald-500 grid place-items-center mx-auto border border-emerald-500/20">
          <CheckCircle2 size={32} />
        </div>
        <h3 className="text-lg font-bold text-ink">Review Gate Clear</h3>
        <p className="text-xs text-ink-2 max-w-sm mx-auto">
          All extracted facts from the latest crawler runs have been evaluated. Newly parsed candidate facts will appear here automatically.
        </p>
      </div>
    );
  }

  const bySvc = pending.reduce<Record<string, PendingFact[]>>((acc, f) => {
    (acc[f.service] ??= []).push(f);
    return acc;
  }, {});

  const allPendingIds = pending.map((f) => f.id);
  const isAllSelected = allPendingIds.length > 0 && allPendingIds.every((id) => selected.has(id));

  return (
    <div className="space-y-6">
      {/* ── Sticky Action Toolbar ── */}
      <div className="sticky top-[108px] z-30 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-line bg-paper/95 p-4 shadow-lg backdrop-blur-md">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => onToggleAll(allPendingIds)}
            className="inline-flex items-center gap-1.5 text-xs font-bold text-ink-2 hover:text-ink cursor-pointer border-none bg-transparent"
          >
            {isAllSelected ? (
              <CheckSquare size={16} className="text-amber-500" />
            ) : (
              <Square size={16} className="text-ink-3" />
            )}
            <span>Select All ({pending.length})</span>
          </button>
          <span className="text-xs text-ink-3 font-semibold">|</span>
          <span className="text-xs font-mono font-bold text-amber-600 bg-amber-500/10 px-2 py-0.5 rounded-md">
            {selected.size} selected
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={busy || selected.size === 0}
            onClick={() => onDecide("approved")}
            className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 text-xs font-bold transition-all disabled:opacity-40 cursor-pointer border-none shadow-xs"
          >
            <CheckCircle2 size={14} />
            <span>Approve Selected</span>
          </button>

          <button
            type="button"
            disabled={busy || selected.size === 0}
            onClick={() => onDecide("rejected")}
            className="inline-flex items-center gap-1.5 rounded-xl border border-line hover:border-rose-400 bg-paper hover:bg-rose-50 text-rose-700 dark:text-rose-400 px-4 py-2 text-xs font-bold transition-all disabled:opacity-40 cursor-pointer shadow-xs"
          >
            <XCircle size={14} />
            <span>Reject</span>
          </button>

          <button
            type="button"
            disabled={busy}
            onClick={onWrite}
            className="inline-flex items-center gap-1.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-navy-950 px-4 py-2 text-xs font-black transition-all disabled:opacity-40 cursor-pointer border-none shadow-md"
          >
            <GitBranch size={14} />
            <span>Write Approved to Neo4j</span>
          </button>
        </div>
      </div>

      {/* ── Grouped Facts by Service ── */}
      <div className="space-y-4">
        {Object.entries(bySvc).map(([svc, facts]) => {
          const isOpen = open.has(svc);
          const hasNew = facts.some((f) => f.new_service);
          const serviceFactIds = facts.map((f) => f.id);
          const allServiceSelected = serviceFactIds.every((id) => selected.has(id));

          return (
            <div key={svc} className="rounded-2xl border border-line bg-paper overflow-hidden shadow-2xs">
              {/* Group Header */}
              <div className="flex items-center justify-between px-5 py-4 bg-paper-2 border-b border-line">
                <button
                  type="button"
                  onClick={() =>
                    setOpen((prev) => {
                      const next = new Set(prev);
                      if (next.has(svc)) next.delete(svc);
                      else next.add(svc);
                      return next;
                    })
                  }
                  className="flex items-center gap-3 text-left font-sans cursor-pointer border-none bg-transparent grow"
                >
                  <div className="text-ink-3">
                    {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  </div>
                  <div>
                    <span className="font-mono text-sm font-bold text-ink">{svc}</span>
                    {hasNew && (
                      <span className="ml-2.5 rounded-full bg-amber-500/15 border border-amber-500/25 px-2 py-0.5 text-[10px] font-extrabold text-amber-700 dark:text-amber-300 uppercase">
                        New Service Target
                      </span>
                    )}
                  </div>
                </button>

                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => onToggleAll(serviceFactIds)}
                    className="text-xs font-semibold text-ink-3 hover:text-ink cursor-pointer border-none bg-transparent"
                  >
                    {allServiceSelected ? "Deselect Group" : "Select Group"}
                  </button>
                  <span className="text-xs font-mono font-bold text-ink-2 bg-paper border border-line px-2 py-0.5 rounded-md">
                    {facts.length} fact{facts.length === 1 ? "" : "s"}
                  </span>
                </div>
              </div>

              {/* Facts List */}
              {isOpen && (
                <div className="divide-y divide-line">
                  {facts.map((f) => {
                    const isChecked = selected.has(f.id);
                    return (
                      <label
                        key={f.id}
                        className={`flex items-start gap-4 p-5 cursor-pointer transition-colors ${
                          isChecked ? "bg-amber-500/5" : "hover:bg-paper-2"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => onToggle(f.id)}
                          className="mt-1 h-4 w-4 rounded border-line text-amber-500 focus:ring-amber-500 cursor-pointer"
                        />

                        <div className="min-w-0 grow space-y-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="rounded-lg border border-line bg-paper px-2.5 py-0.5 font-mono text-xs font-bold text-amber-600">
                              {f.predicate}
                            </span>
                            <span className="text-sm font-bold text-ink">
                              {f.value}
                              {f.unit ? ` ${f.unit}` : ""}
                            </span>
                            {f.old && (
                              <span className="text-xs text-rose-600 bg-rose-500/10 px-2 py-0.5 rounded font-mono">
                                was: {f.old}
                              </span>
                            )}
                          </div>

                          {f.quote && (
                            <div className="p-3 rounded-xl bg-paper-2 border border-line/80 text-xs italic text-ink-2 leading-relaxed font-sans">
                              &ldquo;{f.quote}&rdquo;
                            </div>
                          )}

                          <div className="flex items-center gap-2 pt-1 text-[11px] text-ink-3">
                            <span>Source URL:</span>
                            <a
                              href={f.url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 text-amber-600 hover:underline max-w-lg truncate font-mono"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <span>{f.url}</span>
                              <ExternalLink size={11} />
                            </a>
                          </div>
                        </div>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Pages({ files }: { files: FileRow[] | null }) {
  const [filter, setFilter] = useState<string>("all");
  const [search, setSearch] = useState("");

  const rows = useMemo(() => {
    return (files ?? [])
      .filter((f) => f.latest)
      .filter((f) => filter === "all" || f.state === filter)
      .filter(
        (f) =>
          !search ||
          f.url.toLowerCase().includes(search.toLowerCase()) ||
          (f.agency && f.agency.toLowerCase().includes(search.toLowerCase()))
      );
  }, [files, filter, search]);

  const stateBadges: Record<string, { label: string; cls: string }> = {
    read: {
      label: "Read & Parsed",
      cls: "bg-emerald-500/15 border-emerald-500/25 text-emerald-600 dark:text-emerald-400",
    },
    to_read: {
      label: "Pending Read",
      cls: "bg-amber-500/15 border-amber-500/25 text-amber-600 dark:text-amber-400",
    },
    changed: {
      label: "Content Changed",
      cls: "bg-amber-500/15 border-amber-500/25 text-amber-600 dark:text-amber-400",
    },
    nothing: {
      label: "Noise (Skipped)",
      cls: "bg-paper-3 border-line text-ink-3",
    },
  };

  return (
    <div className="space-y-6">
      {/* ── Search & Filter Bar ── */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4">
        <div className="flex flex-wrap gap-2">
          {["all", "read", "to_read", "nothing"].map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setFilter(s)}
              className={`rounded-xl px-3.5 py-1.5 text-xs font-bold transition-all cursor-pointer border ${
                filter === s
                  ? "bg-navy-900 text-white border-navy-900 shadow-xs"
                  : "bg-paper-2 text-ink-2 border-line hover:border-amber-400/50"
              }`}
            >
              {s === "all" ? "All Pages" : s.replace("_", " ")}
            </button>
          ))}
        </div>

        <div className="relative w-full sm:w-72">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-3 pointer-events-none" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search crawled URLs or agencies..."
            className="w-full pl-9 pr-3 py-1.5 text-xs rounded-xl border border-line bg-paper-2 text-ink placeholder:text-ink-3 focus:outline-none focus:border-amber-500"
          />
        </div>
      </div>

      {/* ── Pages Table ── */}
      <div className="overflow-x-auto rounded-2xl border border-line bg-paper shadow-2xs">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-line bg-paper-2 text-[11px] font-extrabold uppercase tracking-wider text-ink-3">
              <th className="px-5 py-3.5">Crawled Government URL</th>
              <th className="px-4 py-3.5">Department / Agency</th>
              <th className="px-4 py-3.5">Signals</th>
              <th className="px-4 py-3.5">Extraction State</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line text-xs font-sans">
            {rows.map((f) => {
              const badge = stateBadges[f.state] ?? { label: f.state, cls: "bg-paper-3 text-ink-3" };
              return (
                <tr key={f.url} className="hover:bg-paper-2/60 transition-colors">
                  <td className="px-5 py-3.5 max-w-md truncate font-mono text-ink">
                    <a
                      href={f.url}
                      target="_blank"
                      rel="noreferrer"
                      className="hover:text-amber-600 transition-colors"
                    >
                      {f.url}
                    </a>
                  </td>
                  <td className="px-4 py-3.5 text-ink-2 font-medium">{f.agency ?? "—"}</td>
                  <td className="px-4 py-3.5 font-mono text-xs text-ink-2 font-semibold">
                    {f.signals || "—"}
                  </td>
                  <td className="px-4 py-3.5">
                    <span
                      className={`inline-block px-2.5 py-0.5 rounded-full text-[11px] font-bold border ${badge.cls}`}
                    >
                      {badge.label}
                    </span>
                  </td>
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr>
                <td colSpan={4} className="px-5 py-8 text-center text-xs text-ink-3 font-medium">
                  No crawled pages matching the active filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
