import { useEffect, useMemo, useState, useCallback, useRef } from "react";
import {
  Database, GitBranch, FileText, CheckCircle2, XCircle, RefreshCw,
  AlertTriangle, Clock, Link2, Loader2, ChevronDown, ChevronRight,
} from "lucide-react";
import BrandMark from "../components/BrandMark";
import { adminApi, departmentOf, DEPARTMENTS, type FileRow, type GraphData, type PendingFact, type Status } from "../lib/adminApi";

type Key = "status" | "files" | "graph" | "pending";
type Tab = "overview" | "review" | "pages";

/** Admin dashboard -- Component 2 (crawl, LLM extraction, review gate, graph).
 *
 * Real data only: every number comes from the live C2 backend (Postgres `c2`
 * schema + Neo4j), through /c2-api. Approve/reject/write call the actual
 * review gate -- the same one the CLI uses, so a decision made here is a
 * real decision, not a demo of one. */
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

  // React's StrictMode double-fires effects in dev, so the same key (e.g. 'files') can be
  // requested twice back to back. Guard per key, not globally -- an in-flight 'files' call
  // must never block an unrelated 'graph' call, only a second 'files' call racing it.
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

  useEffect(() => { load(["status", "pending"]); }, [load]);
  useEffect(() => {
    if (tab === "overview" && !graph) load(["files", "graph"]);
    if (tab === "pages" && !files) load(["files"]);
  }, [tab, graph, files, load]);

  const byDept = useMemo(() => {
    if (!files) return null;
    // "total" counts only pages worth reading (gate_send): a page with no fee/document/
    // prerequisite wording is correctly never read, and counting it as "missing" would make
    // a fully-done department look incomplete.
    const out = Object.fromEntries(
      DEPARTMENTS.map((d) => [d.key, { total: 0, read: 0, skipped: 0 }]),
    ) as Record<string, { total: number; read: number; skipped: number }>;
    for (const f of files) {
      if (!f.latest) continue;
      const dep = departmentOf(f.url);
      if (!dep) continue;
      if (!f.gate_send && f.state !== "read") { out[dep.key].skipped += 1; continue; }
      out[dep.key].total += 1;
      if (f.state === "read") out[dep.key].read += 1;
    }
    return out;
  }, [files]);

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
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
        setToast(`Rejected ${r.decided}`);
        setSelected(new Set());
        await load(["pending"]);
      } catch (e) { setToast(`Failed: ${e instanceof Error ? e.message : e}`); } finally { setBusy(false); }
      return;
    }
    setBusy(true);
    try {
      const r = await adminApi.decide([...selected], "approved", "reviewed in admin dashboard");
      setToast(`Approved ${r.decided}`);
      setSelected(new Set());
      await load(["pending"]);
    } catch (e) { setToast(`Failed: ${e instanceof Error ? e.message : e}`); } finally { setBusy(false); }
  }

  async function writeToGraph() {
    setBusy(true);
    try {
      const r = await adminApi.write();
      setToast(`Wrote ${r.new} new, ${r.changed} changed, ${r.failed?.length ?? 0} failed`);
      await load(["pending", "graph"]);
    } catch (e) { setToast(`Failed: ${e instanceof Error ? e.message : e}`); } finally { setBusy(false); }
  }

  const loading =
    tab === "overview" ? !status || !files || !graph
    : tab === "pages" ? !status || !files
    : !status || !pending;

  return (
    <div className="min-h-screen bg-paper text-ink">
      <header className="sticky top-0 z-10 border-b border-line bg-paper/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-sp-4 px-sp-5 py-sp-4">
          <BrandMark />
          <div className="grow">
            <h1 className="text-lg font-semibold text-ink">Knowledge graph admin</h1>
            <p className="text-xs text-ink-2">Component 2 &middot; crawl, extraction, review gate, graph</p>
          </div>
          <StatusPill status={status} />
          <button
            onClick={() => load(tab === "overview" ? ["status", "files", "graph"] : tab === "pages" ? ["status", "files"] : ["status", "pending"])}
            className="flex items-center gap-sp-2 rounded-r-md border border-line px-sp-3 py-sp-2 text-sm text-ink-2 hover:bg-paper-2"
          >
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
        <nav className="mx-auto flex max-w-6xl gap-sp-2 px-sp-5 pb-sp-2">
          {([
            ["overview", "Overview"],
            ["review", `Review queue${pending ? ` (${pending.length})` : ""}`],
            ["pages", "Pages"],
          ] as [Tab, string][]).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`rounded-r-pill px-sp-4 py-sp-1 text-sm transition ${
                tab === key ? "bg-brand text-brand-ink font-medium" : "text-ink-2 hover:bg-paper-2"
              }`}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>

      <main className="mx-auto max-w-6xl px-sp-5 py-sp-6">
        {error && (
          <div className="mb-sp-5 flex items-start gap-sp-3 rounded-r-lg border border-amber-300 bg-amber-50 p-sp-4 text-sm text-amber-800">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            <div>
              <div className="font-medium">Can&apos;t reach the C2 backend</div>
              <div className="text-xs opacity-80">{error}</div>
              <div className="mt-sp-2 text-xs opacity-80">
                Start it with: <code className="rounded bg-paper px-1.5 py-0.5 font-mono">python -m app.admin_ui</code> in{" "}
                <code className="rounded bg-paper px-1.5 py-0.5 font-mono">components/c2-knowledge-graph/service</code>
              </div>
            </div>
          </div>
        )}

        {loading && !error && (
          <div className="flex items-center gap-sp-2 py-sp-8 text-ink-2">
            <Loader2 size={16} className="animate-spin" /> Loading live data&hellip;
          </div>
        )}

        {!loading && tab === "overview" && <Overview graph={graph} byDept={byDept} />}
        {!loading && tab === "review" && (
          <ReviewQueue
            pending={pending}
            selected={selected}
            onToggle={toggle}
            onDecide={decide}
            onWrite={writeToGraph}
            busy={busy}
          />
        )}
        {!loading && tab === "pages" && <Pages files={files} />}
      </main>

      {toast && (
        <div className="fixed bottom-sp-5 left-1/2 -translate-x-1/2 rounded-r-lg border border-line bg-ink px-sp-4 py-sp-2 text-sm text-paper shadow-lg">
          {toast}
          <button className="ml-sp-3 text-paper/60 hover:text-paper" onClick={() => setToast(null)}>&times;</button>
        </div>
      )}
    </div>
  );
}

function StatusPill({ status }: { status: Status | null }) {
  if (!status) return null;
  const ok = status.postgres && status.neo4j;
  return (
    <div className={`flex items-center gap-sp-2 rounded-r-pill px-sp-3 py-sp-1 text-xs font-medium ${ok ? "bg-green-100 text-green-800" : "bg-amber-100 text-amber-800"}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${ok ? "bg-green-600" : "bg-amber-600"}`} />
      {ok ? "Live: Postgres + Neo4j connected" : "Partially connected"}
    </div>
  );
}

function StatCard({ icon: Icon, label, value }: { icon: typeof Database; label: string; value: number | string }) {
  return (
    <div className="rounded-r-lg border border-line bg-paper-2 p-sp-4">
      <div className="flex items-center gap-sp-2 text-ink-2">
        <Icon size={15} />
        <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
      </div>
      <div className="mt-sp-2 text-2xl font-semibold text-ink">{value}</div>
    </div>
  );
}

function Overview({ graph, byDept }: { graph: GraphData | null; byDept: Record<string, { total: number; read: number; skipped: number }> | null }) {
  const g = graph?.summary;
  return (
    <div className="flex flex-col gap-sp-6">
      <section>
        <h2 className="mb-sp-3 text-sm font-semibold text-ink-2">Graph totals</h2>
        <div className="grid grid-cols-2 gap-sp-3 sm:grid-cols-3 lg:grid-cols-6">
          <StatCard icon={Database} label="Services" value={g?.services ?? "—"} />
          <StatCard icon={Link2} label="Agencies" value={g?.agencies ?? "—"} />
          <StatCard icon={FileText} label="Documents" value={g?.documents ?? "—"} />
          <StatCard icon={CheckCircle2} label="Facts (current)" value={g?.["facts (current)"] ?? "—"} />
          <StatCard icon={Clock} label="Facts (all versions)" value={g?.["facts (all versions)"] ?? "—"} />
          <StatCard icon={GitBranch} label="REQUIRES edges" value={g?.["REQUIRES edges"] ?? "—"} />
        </div>
      </section>

      <section>
        <h2 className="mb-sp-3 text-sm font-semibold text-ink-2">Departments</h2>
        <div className="grid grid-cols-1 gap-sp-3 sm:grid-cols-2 lg:grid-cols-4">
          {DEPARTMENTS.map((d) => {
            const c = byDept?.[d.key] ?? { total: 0, read: 0, skipped: 0 };
            const pct = c.total ? Math.round((c.read / c.total) * 100) : 0;
            const waiting = c.total - c.read;
            return (
              <div key={d.key} className="rounded-r-lg border border-line bg-paper-2 p-sp-4">
                <div className="text-sm font-medium text-ink">{d.label}</div>
                <div className="mt-sp-2 flex items-baseline gap-sp-2">
                  <span className="text-xl font-semibold text-ink">{c.read}</span>
                  <span className="text-xs text-ink-2">/ {c.total} pages with facts to read</span>
                </div>
                <div className="mt-sp-2 h-1.5 w-full overflow-hidden rounded-r-pill bg-paper-3">
                  <div className="h-full bg-brand" style={{ width: `${pct}%` }} />
                </div>
                {waiting > 0 && <div className="mt-sp-2 text-xs text-amber-700">{waiting} waiting to be read</div>}
                <div className="mt-sp-1 text-xs text-ink-3">{c.skipped} other page(s) skipped (no signal)</div>
              </div>
            );
          })}
        </div>
      </section>

      {graph && graph.empty_services.length > 0 && (
        <section>
          <h2 className="mb-sp-3 flex items-center gap-sp-2 text-sm font-semibold text-amber-700">
            <AlertTriangle size={14} /> Services with no facts yet ({graph.empty_services.length})
          </h2>
          <div className="flex flex-wrap gap-sp-2">
            {graph.empty_services.map((id) => (
              <span key={id} className="rounded-r-pill border border-line bg-paper-2 px-sp-3 py-sp-1 font-mono text-xs text-ink-2">{id}</span>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function ReviewQueue({ pending, selected, onToggle, onDecide, onWrite, busy }: {
  pending: PendingFact[] | null;
  selected: Set<number>;
  onToggle: (id: number) => void;
  onDecide: (d: "approved" | "rejected") => void;
  onWrite: () => void;
  busy: boolean;
}) {
  const [open, setOpen] = useState<Set<string>>(() => new Set());
  if (!pending?.length) {
    return (
      <div className="flex flex-col items-center gap-sp-3 py-sp-8 text-center text-ink-2">
        <CheckCircle2 size={28} className="text-green-600" />
        <div className="text-sm">Nothing waiting for review.</div>
      </div>
    );
  }

  const bySvc = pending.reduce<Record<string, PendingFact[]>>((acc, f) => {
    (acc[f.service] ??= []).push(f);
    return acc;
  }, {});

  return (
    <div className="flex flex-col gap-sp-4">
      <div className="sticky top-[104px] z-10 flex items-center gap-sp-3 rounded-r-lg border border-line bg-paper p-sp-3 shadow-sm">
        <span className="text-sm text-ink-2">{selected.size} selected of {pending.length}</span>
        <div className="grow" />
        <button disabled={busy || selected.size === 0} onClick={() => onDecide("approved")}
          className="flex items-center gap-sp-2 rounded-r-md bg-green-600 px-sp-3 py-sp-2 text-sm font-medium text-white disabled:opacity-40">
          <CheckCircle2 size={14} /> Approve
        </button>
        <button disabled={busy || selected.size === 0} onClick={() => onDecide("rejected")}
          className="flex items-center gap-sp-2 rounded-r-md border border-line px-sp-3 py-sp-2 text-sm font-medium text-ink-2 hover:bg-paper-2 disabled:opacity-40">
          <XCircle size={14} /> Reject
        </button>
        <button disabled={busy} onClick={onWrite}
          className="flex items-center gap-sp-2 rounded-r-md bg-brand px-sp-3 py-sp-2 text-sm font-medium text-brand-ink disabled:opacity-40">
          <GitBranch size={14} /> Write approved to graph
        </button>
      </div>

      {Object.entries(bySvc).map(([svc, facts]) => {
        const isOpen = open.has(svc);
        const hasNew = facts.some((f) => f.new_service);
        return (
          <div key={svc} className="rounded-r-lg border border-line">
            <button
              className="flex w-full items-center gap-sp-2 px-sp-4 py-sp-3 text-left"
              onClick={() => setOpen((prev) => {
                const next = new Set(prev);
                next.has(svc) ? next.delete(svc) : next.add(svc);
                return next;
              })}
            >
              {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              <span className="font-mono text-sm text-ink">{svc}</span>
              {hasNew && <span className="rounded-r-pill bg-brand-soft px-sp-2 py-0.5 text-xs text-brand-ink">new service</span>}
              <span className="ml-auto text-xs text-ink-2">{facts.length} fact(s)</span>
            </button>
            {isOpen && (
              <div className="border-t border-line">
                {facts.map((f) => (
                  <label key={f.id} className="flex cursor-pointer items-start gap-sp-3 border-b border-line px-sp-4 py-sp-3 last:border-b-0 hover:bg-paper-2">
                    <input type="checkbox" checked={selected.has(f.id)} onChange={() => onToggle(f.id)} className="mt-1" />
                    <div className="min-w-0 grow">
                      <div className="flex flex-wrap items-center gap-sp-2 text-sm">
                        <span className="rounded border border-line px-1.5 py-0.5 font-mono text-xs text-ink-2">{f.predicate}</span>
                        <span className="text-ink">{f.value}{f.unit ? ` ${f.unit}` : ""}</span>
                        {f.old && <span className="text-xs text-amber-700">was: {f.old}</span>}
                      </div>
                      {f.quote && <div className="mt-sp-1 line-clamp-2 text-xs italic text-ink-2">&ldquo;{f.quote}&rdquo;</div>}
                      <a href={f.url} target="_blank" rel="noreferrer" className="mt-sp-1 inline-block truncate text-xs text-ink-3 hover:text-brand">{f.url}</a>
                    </div>
                  </label>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function Pages({ files }: { files: FileRow[] | null }) {
  const [filter, setFilter] = useState<string>("all");
  const rows = useMemo(
    () => (files ?? []).filter((f) => f.latest && (filter === "all" || f.state === filter)),
    [files, filter],
  );
  const stateColor: Record<string, string> = {
    read: "bg-green-100 text-green-800",
    to_read: "bg-amber-100 text-amber-800",
    changed: "bg-amber-100 text-amber-800",
    nothing: "bg-paper-3 text-ink-3",
  };

  return (
    <div className="flex flex-col gap-sp-4">
      <div className="flex gap-sp-2">
        {["all", "read", "to_read", "nothing"].map((s) => (
          <button key={s} onClick={() => setFilter(s)}
            className={`rounded-r-pill px-sp-3 py-sp-1 text-xs ${filter === s ? "bg-ink text-paper" : "border border-line text-ink-2"}`}>
            {s.replace("_", " ")}
          </button>
        ))}
      </div>
      <div className="overflow-x-auto rounded-r-lg border border-line">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs text-ink-2">
              <th className="px-sp-3 py-sp-2">Page</th>
              <th className="px-sp-3 py-sp-2">Agency</th>
              <th className="px-sp-3 py-sp-2">Signals</th>
              <th className="px-sp-3 py-sp-2">State</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((f) => (
              <tr key={f.url} className="border-b border-line last:border-b-0">
                <td className="max-w-md truncate px-sp-3 py-sp-2 font-mono text-xs text-ink">{f.url}</td>
                <td className="px-sp-3 py-sp-2 text-xs text-ink-2">{f.agency ?? "—"}</td>
                <td className="px-sp-3 py-sp-2 font-mono text-xs text-ink-2">{f.signals}</td>
                <td className="px-sp-3 py-sp-2">
                  <span className={`rounded-r-pill px-sp-2 py-0.5 text-xs ${stateColor[f.state] ?? "bg-paper-3 text-ink-3"}`}>{f.state}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
