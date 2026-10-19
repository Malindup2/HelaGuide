import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import fixture from "./fixtures/pipeline-trace.json";
import { C4Api } from "../api/client";
import { InspectorApi, parseTrace, parseTraceIndex } from "../inspector/api";
import { InspectorController, inspectorAddress, inspectorTarget, isInspectorAddress } from "../inspector/controller";
import { TraceView } from "../inspector/TraceView";
import type { PipelineTrace } from "../inspector/types";

const sid = fixture.records.presentation.session_id;
const eid = fixture.records.presentation.exposure_id;
function trace() { return structuredClone(fixture); }
function index(t = trace()) {
  const p = t.records.presentation;
  return { schema_version: "c4-pipeline-trace-index-1.0", current_guidance: t.current.guidance,
    current_request_routing: "adaptive", standard_guidance_history: "not_persisted_no_policy_or_learning_record",
    explanation: "Standard guidance has no persisted policy or learning trace.", presentations: [{
      exposure_id: p.exposure_id, presentation_id: p.presentation_id, decision_id: p.decision_id,
      graph_fingerprint: p.graph_fingerprint, offered_at: t.records.policy_offer.offer.offered_at,
      configuration: p.configuration, selection_posterior_revision: t.selection.selection_posterior_revision,
      acknowledged: true, feedback_accepted: true,
    }] };
}
function setup() {
  const api = new InspectorApi();
  vi.spyOn(api, "profiles").mockResolvedValue([]);
  const readIndex = vi.spyOn(api, "index").mockResolvedValue(parseTraceIndex(index(), sid));
  const readTrace = vi.spyOn(api, "trace").mockResolvedValue(parseTrace(trace(), sid, eid));
  const address = vi.fn();
  return { api, readIndex, readTrace, address, controller: new InspectorController(api, address) };
}
describe("pipeline trace contracts", () => {
  it("accepts an actual isolated backend trace and distinguishes historical/current revisions", () => {
    const t = parseTrace(trace(), sid, eid);
    expect(t.selection.selection_posterior_revision).toBe(0);
    expect(t.learning.reward).toBe(0);
    expect(t.learning.resulting_posterior_revision).toBe(1);
    expect(t.current.shared_posterior_revision).toBe(2);
    expect(parseTraceIndex(index(), sid).presentations).toHaveLength(1);
  });
  it("rejects a different session or exposure", () => {
    expect(() => parseTrace(trace(), "guest:" + "f".repeat(32), eid)).toThrow();
    expect(() => parseTrace(trace(), sid, "exposure:missing")).toThrow();
    expect(() => parseTraceIndex(index(), "guest:other")).toThrow();
  });
  it("rejects unsupported schema versions", () => {
    const t = trace(); t.schema_version = "future";
    expect(() => parseTrace(t, sid, eid)).toThrow();
    expect(() => parseTraceIndex({ ...index(), schema_version: "future" }, sid)).toThrow();
  });
  it("rejects scores fabricated for rejected candidates and missing candidate evaluations", () => {
    const t = trace(); const rejected = t.candidates.find(c => !c.feasible)!;
    rejected.score = t.candidates.find(c => c.score)!.score;
    expect(() => parseTrace(t, sid, eid)).toThrow();
    expect(() => parseTrace({ ...trace(), candidates: [] }, sid, eid)).toThrow();
  });
  it("rejects duplicated candidates or inconsistent selection totals", () => {
    const t = trace(); t.candidates[1] = t.candidates[0];
    expect(() => parseTrace(t, sid, eid)).toThrow();
    const t2 = trace(); t2.selection.feasible_count++;
    expect(() => parseTrace(t2, sid, eid)).toThrow();
  });
  it("keeps incomplete feature exact values unknown and rejects fabricated zeroes", () => {
    const t = trace(); const m = t.structural_features[0].measurement;
    m.completeness = "partial"; m.exact_value = null as unknown as number; m.normalized_exact = null as unknown as number;
    expect(parseTrace(t, sid, eid).structural_features[0].measurement.exact_value).toBeNull();
    m.exact_value = 0;
    expect(() => parseTrace(t, sid, eid)).toThrow();
  });
  it("does not accept missing reward as a zero-reward update", () => {
    const t = trace(); t.learning.status = "no_accepted_feedback";
    expect(() => parseTrace(t, sid, eid)).toThrow();
  });
  it("accepts forced decisions with moments but no fabricated sampled scores", () => {
    const t = trace(); t.selection.selection_mode = "forced"; t.selection.sampled_candidate_count = 0;
    for (const c of t.candidates) if (c.score) { c.score.sampled_score = null as unknown as number; c.score_status = "recorded_moments_not_sampled"; }
    const parsed = parseTrace(t, sid, eid);
    expect(renderToStaticMarkup(<TraceView trace={parsed} />)).toContain("Not sampled");
  });
  it("accepts frozen wording styles as literal strings, not objects", () => {
    const t = trace(); t.records.wording_style = "concise" as unknown as null;
    expect(parseTrace(t, sid, eid).records.wording_style).toBe("concise");
    t.records.wording_style = "future" as unknown as null;
    expect(() => parseTrace(t, sid, eid)).toThrow();
  });
  it("accepts standard routing with empty adaptive history", () => {
    const i = index(); i.current_request_routing = "standard"; i.current_guidance.personalization_enabled = false; i.presentations = [];
    expect(parseTraceIndex(i, sid).presentations).toEqual([]);
  });
});
describe("read-only Inspector requests and continuity", () => {
  it("uses only encoded, uncached GET requests through the existing API transport", async () => {
    const fetcher = vi.fn(async (url: string | URL | Request) => new Response(JSON.stringify(String(url).endsWith("/pipeline-traces") ? index() : trace()), { status: 200 }));
    const api = new InspectorApi(new C4Api("http://example.test", fetcher as typeof fetch));
    await api.index(sid); await api.trace(sid, eid); await api.trace(sid, eid);
    expect(fetcher).toHaveBeenCalledTimes(3);
    for (const [url, options] of fetcher.mock.calls as unknown as [string, RequestInit][]) {
      expect(options.method).toBe("GET"); expect(options.cache).toBe("no-store"); expect(options.body).toBeUndefined();
      expect(url).toContain(encodeURIComponent(sid));
    }
    expect(String(fetcher.mock.calls[1][0])).toContain(encodeURIComponent(eid));
  });
  it("retains a deep link without mounting or creating a citizen session", () => {
    const hash = inspectorAddress(sid, eid);
    expect(isInspectorAddress(hash)).toBe(true);
    expect(isInspectorAddress("#trace-input")).toBe(false);
    expect(inspectorTarget(hash)).toEqual({ session: sid, exposure: eid });
  });
  it("preserves the deep-linked exposure while an effect remount replays history loading", async () => {
    const s = setup(); let hash = inspectorAddress(sid, eid);
    const controller = new InspectorController(s.api, next => { hash = next; });
    let resolve!: (v: ReturnType<typeof parseTraceIndex>) => void;
    s.readIndex.mockReturnValueOnce(new Promise(r => { resolve = r; }));
    const first = controller.open(sid, eid);
    expect(inspectorTarget(hash).exposure).toBe(eid);
    controller.dispose();
    const target = inspectorTarget(hash);
    await controller.open(target.session, target.exposure);
    resolve(parseTraceIndex(index(), sid)); await first;
    expect(s.readTrace).toHaveBeenCalledExactlyOnceWith(sid, eid);
  });
  it("opens latest saved trace and refreshes the exact exposure", async () => {
    const s = setup(); await s.controller.open(sid); await s.controller.refresh();
    expect(s.readTrace).toHaveBeenNthCalledWith(2, sid, eid);
    expect(s.controller.snapshot().trace?.records.presentation.exposure_id).toBe(eid);
    expect(s.address).toHaveBeenLastCalledWith(inspectorAddress(sid, eid));
  });
  it("does not silently replace a deleted deep-linked presentation", async () => {
    const s = setup(); await s.controller.open(sid, "exposure:deleted");
    expect(s.readTrace).not.toHaveBeenCalled();
    expect(s.controller.snapshot().trace).toBeNull();
    expect(s.controller.snapshot().error).toContain("not in the saved history");
  });
  it("displays empty adaptive history without requesting a trace", async () => {
    const s = setup(); s.readIndex.mockResolvedValue({ ...parseTraceIndex(index(), sid), presentations: [] });
    await s.controller.open(sid); expect(s.readTrace).not.toHaveBeenCalled();
    expect(s.controller.snapshot().index?.presentations).toEqual([]);
  });
  it("rejects invalid session entry without a network request", async () => {
    const s = setup(); await s.controller.open("invalid"); expect(s.readIndex).not.toHaveBeenCalled();
    expect(s.controller.snapshot().loading).toBeNull(); expect(s.controller.snapshot().trace).toBeNull();
  });
  it("clears the old trace immediately and ignores a late response after changing session", async () => {
    const s = setup(); await s.controller.open(sid);
    let resolve!: (value: PipelineTrace) => void;
    s.readTrace.mockReturnValueOnce(new Promise(r => { resolve = r; }));
    const pending = s.controller.select(eid);
    expect(s.controller.snapshot().trace).toBeNull();
    const other = "guest:" + "e".repeat(32);
    s.readIndex.mockRejectedValueOnce(new Error("Other session unavailable"));
    await s.controller.open(other); resolve(parseTrace(trace(), sid, eid)); await pending;
    expect(s.controller.snapshot().session).toBe(other); expect(s.controller.snapshot().trace).toBeNull();
    expect(s.controller.snapshot().error).toBe("Other session unavailable");
  });
  it("ignores a late history response and responses after unmount", async () => {
    const s = setup(); let resolve!: (v: ReturnType<typeof parseTraceIndex>) => void;
    s.readIndex.mockReturnValueOnce(new Promise(r => { resolve = r; }));
    const pending = s.controller.open(sid); s.controller.dispose(); resolve(parseTraceIndex(index(), sid)); await pending;
    expect(s.readTrace).not.toHaveBeenCalled(); expect(s.controller.snapshot().index).toBeNull();
  });
  it("surfaces trace errors instead of displaying a previous trace", async () => {
    const s = setup(); await s.controller.open(sid); s.readTrace.mockRejectedValueOnce(new Error("HTTP 503"));
    await s.controller.select(eid); expect(s.controller.snapshot().trace).toBeNull(); expect(s.controller.snapshot().error).toBe("HTTP 503");
  });
});
describe("Inspector evidence rendering", () => {
  it("renders scores, provenance, graph and distinct update/current revisions without effects", () => {
    const html = renderToStaticMarkup(<TraceView trace={parseTrace(trace(), sid, eid)} />);
    for (const text of ["Canonical graph", "Seven source-based", "Context at selection", "Not scored", "Linear surrogate scores are not probabilities", "No resampling", "snapshot not available", "need more / too much", "Current shared revision", "Evidence boundaries"]) expect(html).toContain(text);
    expect(html).toContain("Recorded service dependencies"); expect(html).toContain("Recorded action prerequisites");
  });
  it("labels absent feedback and absent exact measurements without fabricating a reward", () => {
    const t = parseTrace(trace(), sid, eid);
    t.learning = { ...t.learning, status: "no_accepted_feedback", reward: null, revision_immediately_before_update: null, resulting_posterior_revision: null, linear_delta_b: null };
    t.structural_features[0].measurement = { ...t.structural_features[0].measurement, completeness: "unknown", exact_value: null, normalized_exact: null };
    const html = renderToStaticMarkup(<TraceView trace={t} />);
    expect(html).toContain("No accepted reward"); expect(html).toContain("Unknown"); expect(html).not.toContain("Derived update terms");
  });
});
