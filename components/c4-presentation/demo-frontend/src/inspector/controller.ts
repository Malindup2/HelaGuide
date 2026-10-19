import { errorMessage } from "../api/client";
import type { DemoProfile } from "../api/types";
import { InspectorApi } from "./api";
import type { PipelineTrace, TraceIndex } from "./types";

export interface InspectorState {
  profiles: DemoProfile[]; session: string; exposure: string;
  index: TraceIndex | null; trace: PipelineTrace | null;
  loading: "profiles" | "history" | "trace" | null; error: string | null;
}
export function inspectorAddress(session = "", exposure = "") {
  const query = new URLSearchParams();
  if (session) query.set("session", session);
  if (exposure) query.set("exposure", exposure);
  return "#pipeline-inspector" + (query.size ? "?" + query : "");
}
export function inspectorTarget(hash: string) {
  const query = new URLSearchParams(hash.split("?")[1] ?? "");
  return { session: query.get("session") ?? "", exposure: query.get("exposure") ?? "" };
}
export const isInspectorAddress = (hash: string) => hash.split("?")[0] === "#pipeline-inspector";

export class InspectorController {
  private state: InspectorState = { profiles: [], session: "", exposure: "", index: null, trace: null, loading: null, error: null };
  private listeners = new Set<() => void>();
  private generation = 0;
  private profileGeneration = 0;
  constructor(private readonly api = new InspectorApi(), private readonly address: (hash: string) => void = () => {}) {}
  snapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private update(patch: Partial<InspectorState>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach(listener => listener());
  }
  dispose() { this.generation++; this.profileGeneration++; }
  async profiles() {
    const request = ++this.profileGeneration;
    this.update({ error: null });
    try {
      const profiles = await this.api.profiles();
      if (request === this.profileGeneration) this.update({ profiles });
    } catch (error) {
      if (request === this.profileGeneration) this.update({ error: errorMessage(error) });
    }
  }
  async open(session: string, exposure = "") {
    const request = ++this.generation;
    this.update({ session, exposure: "", index: null, trace: null, error: null, loading: "history" });
    // Preserve the requested exposure while loading, including StrictMode's effect replay.
    this.address(inspectorAddress(session, exposure));
    if (!/^guest:[0-9a-f]{32}$/.test(session)) {
      this.update({ loading: null, error: "Enter a saved session ID in the form guest: followed by 32 hexadecimal characters." });
      return;
    }
    try {
      const index = await this.api.index(session);
      if (request !== this.generation) return;
      this.update({ index, loading: null });
      const target = exposure || index.presentations.at(-1)?.exposure_id;
      if (target) await this.select(target);
    } catch (error) {
      if (request === this.generation) this.update({ error: errorMessage(error), loading: null });
    }
  }
  async select(exposure: string) {
    const request = ++this.generation;
    const { session, index } = this.state;
    this.update({ exposure, trace: null, error: null, loading: "trace" });
    this.address(inspectorAddress(session, exposure));
    if (!index?.presentations.some(p => p.exposure_id === exposure)) {
      this.update({ error: "This presentation is not in the saved history for this session. Refresh history or choose another presentation.", loading: null });
      return;
    }
    try {
      const trace = await this.api.trace(session, exposure);
      if (request === this.generation) this.update({ trace, loading: null });
    } catch (error) {
      if (request === this.generation) this.update({ error: errorMessage(error), loading: null });
    }
  }
  refresh() { return this.open(this.state.session, this.state.exposure); }
}
