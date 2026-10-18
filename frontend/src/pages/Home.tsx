import { useState } from "react";
import { ShieldCheck, Zap, Users, Clock, ArrowRight } from "lucide-react";
import BrandMark from "../components/BrandMark";
import { askForGuidance } from "../api/gateway";
import type { Render } from "../api/types";

const sessionId = `anon-${Math.random().toString(36).slice(2, 8)}`;

const CORE_VALUES = [
  { icon: Users, title: "Citizen-centric", desc: "Built around what people actually need to do" },
  { icon: Zap, title: "Fast", desc: "One question, the full ordered workflow" },
  { icon: ShieldCheck, title: "Traceable", desc: "Every fact points back to its government source" },
  { icon: Clock, title: "Kept current", desc: "Re-checked against the real sites, not a one-off copy" },
];

/** Landing page -- the first real screen in this scaffold. Intentionally thin:
 * the full citizen conversation flow, guided mode, and the rest of the
 * experience are built incrementally by the team over the coming months.
 * This page exists to carry the theme, the brand, and a working path to a
 * real answer through the actual gateway contract. */
export default function Home() {
  const [text, setText] = useState("");
  const [result, setResult] = useState<Render | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await askForGuidance(sessionId, text));
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-paper text-ink">
      <a href="#main" className="skip-link">Skip to content</a>

      <header className="border-b border-line">
        <div className="mx-auto flex max-w-4xl items-center gap-sp-3 px-sp-5 py-sp-4">
          <BrandMark size={36} />
          <span className="text-lg font-semibold text-ink">HelaGuide</span>
        </div>
      </header>

      <main id="main" className="mx-auto max-w-4xl px-sp-5 py-sp-8">
        <div className="rounded-r-pill bg-brand-soft px-sp-4 py-sp-1 text-xs font-medium text-brand-ink inline-block">
          AI-powered government service guide
        </div>

        <h1 className="mt-sp-5 text-4xl font-semibold leading-tight text-ink sm:text-5xl">
          Ask once. Get the full workflow.
        </h1>
        <p className="mt-sp-3 max-w-xl text-ink-2">
          Tell HelaGuide what you need -- a passport, an NIC, a birth certificate -- and get
          the ordered steps, documents, and fees across every department involved, sourced
          from the real government sites.
        </p>

        <form onSubmit={submit} className="mt-sp-6 flex gap-sp-2">
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="What do you need? e.g. passport ekak ganna one"
            className="flex-1 rounded-r-lg border border-line px-sp-4 py-sp-3 text-ink outline-none focus:border-brand"
          />
          <button
            disabled={busy || !text.trim()}
            className="flex items-center gap-sp-2 rounded-r-lg bg-brand px-sp-5 py-sp-3 font-medium text-brand-ink disabled:opacity-50"
          >
            {busy ? "Asking…" : "Ask"} <ArrowRight size={16} />
          </button>
        </form>

        {error && <p className="mt-sp-3 text-sm text-red-700">{error}</p>}

        {result && (
          <ol className="mt-sp-6 flex flex-col gap-sp-4">
            {result.steps.map((s) => (
              <li key={s.order} className="rounded-r-lg border border-line p-sp-4">
                <div className="flex items-baseline justify-between gap-sp-3">
                  <span className="font-medium text-ink">{s.order}. {s.title}</span>
                  <span className="text-sm text-ink-2">{s.fee_display}</span>
                </div>
                <p className="mt-sp-1 text-sm text-ink-2">{s.body}</p>
                {s.documents.length > 0 && (
                  <p className="mt-sp-2 text-xs text-ink-3">Bring: {s.documents.join(", ")}</p>
                )}
                {s.warning && <p className="mt-sp-2 text-xs text-amber-700">&#9888; {s.warning}</p>}
              </li>
            ))}
          </ol>
        )}

        <div className="mt-sp-8 grid grid-cols-2 gap-sp-4 sm:grid-cols-4">
          {CORE_VALUES.map(({ icon: Icon, title, desc }) => (
            <div key={title} className="rounded-r-lg border border-line p-sp-4">
              <Icon size={20} className="text-brand" />
              <div className="mt-sp-2 text-sm font-medium text-ink">{title}</div>
              <div className="mt-sp-1 text-xs text-ink-2">{desc}</div>
            </div>
          ))}
        </div>
      </main>

      <footer className="border-t border-line py-sp-5 text-center text-xs text-ink-3">
        Information is checked against the department's own website, but always confirm
        before relying on it for an official process.
      </footer>
    </div>
  );
}
