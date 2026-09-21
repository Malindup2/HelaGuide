// Placeholder screen so the full path can be exercised end to end.
// The real interface is Dias's (C4) to design.
import { useState } from "react";
import { askForGuidance } from "./api/gateway";
import type { Render } from "./api/types";

const sessionId = `anon-${Math.random().toString(36).slice(2, 8)}`;

export default function App() {
  const [text, setText] = useState("");
  const [result, setResult] = useState<Render | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
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
    <main style={{ maxWidth: 640, margin: "2rem auto", padding: "0 1rem", fontFamily: "system-ui, sans-serif" }}>
      <h1>HelaGuide</h1>
      <form onSubmit={submit} style={{ display: "flex", gap: 8 }}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="What do you need? e.g. passport ekak ganna one"
          style={{ flex: 1, padding: 8 }}
        />
        <button disabled={busy || !text.trim()}>{busy ? "…" : "Ask"}</button>
      </form>

      {error && <p style={{ color: "crimson" }}>{error}</p>}

      {result && (
        <ol>
          {result.steps.map((s) => (
            <li key={s.order} style={{ margin: "1rem 0" }}>
              <strong>{s.title}</strong> · {s.fee_display}
              <div>{s.body}</div>
              {s.documents.length > 0 && <small>Bring: {s.documents.join(", ")}</small>}
              {s.warning && <div style={{ color: "#a15c00" }}>⚠ {s.warning}</div>}
            </li>
          ))}
        </ol>
      )}
    </main>
  );
}
