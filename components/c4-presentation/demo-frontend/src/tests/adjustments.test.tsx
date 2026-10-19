import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import data from "./fixtures/adjustments.json";
import { parseSpec } from "../guidance/contracts";
import { AdjustmentApi, parseAdjustment } from "../adjustments/api";
import { AdjustmentFlow } from "../adjustments/flow";
import { AdjustmentControls, ManualViewFeedback } from "../adjustments/AdjustmentControls";
import traceFixture from "./fixtures/pipeline-trace.json";
import { parseTrace } from "../inspector/api";
import type { PendingAdjustment } from "../adjustments/api";

const root = parseSpec(data.root);
const initial = () => parseAdjustment(structuredClone(data.initial), root);
const adjusted = () => parseAdjustment(structuredClone(data.adjusted), root);
const displayed = () => parseAdjustment(structuredClone(data.displayed), root);
function setup() {
  const api = new AdjustmentApi();
  vi.spyOn(api, "read").mockResolvedValue(initial());
  const send = vi.spyOn(api, "send").mockResolvedValue(adjusted());
  const values = new Map<string, string>();
  const storage = { getItem: (k: string) => values.get(k) ?? null, setItem: (k: string, v: string) => { values.set(k, v); }, removeItem: (k: string) => { values.delete(k); } };
  const flow = new AdjustmentFlow(root, api, storage, "test");
  return { api, send, values, storage, flow };
}
describe("manual-view contracts", () => {
  it("accepts actual backend states across adjustment, display, rating and Undo", () => {
    for (const key of ["initial", "adjusted", "displayed", "rated", "undone"] as const) expect(parseAdjustment(data[key], root).ledger.revision).toBe(data[key].ledger.revision);
    expect(parseAdjustment(data.undone, root).learning_eligible).toBe(false);
    expect(parseAdjustment(data.rated, root).ledger.ratings[0].learning_eligible).toBe(false);
  });
  it("rejects foreign exposure, changed source content, duplicate views and fabricated learning eligibility", () => {
    const wrong = structuredClone(data.adjusted); wrong.ledger.exposure_id = "exposure:foreign";
    expect(() => parseAdjustment(wrong, root)).toThrow();
    const source = structuredClone(data.adjusted); source.spec.explanation.source.graph.disclaimer = "Changed source";
    expect(() => parseAdjustment(source, root)).toThrow();
    const duplicate = structuredClone(data.adjusted); duplicate.ledger.views.push(duplicate.ledger.views[0]);
    expect(() => parseAdjustment(duplicate, root)).toThrow();
    expect(() => parseAdjustment({ ...data.adjusted, learning_eligible: true }, root)).toThrow();
  });
  it("preserves a frozen wording attachment", () => {
    const original = { ...root, prepared_wording: { request_key: "test", graph_fingerprint: root.graph_fingerprint, artifact_digest: null, diagnostics: [], items: [] } };
    expect(parseAdjustment(data.adjusted, original).spec.prepared_wording).toBe(original.prepared_wording);
  });
  it("rejects manual history attached to a different Inspector exposure", () => {
    const foreign = { ...traceFixture, adjustments: data.adjusted };
    expect(() => parseTrace(foreign, traceFixture.records.presentation.session_id, traceFixture.records.presentation.exposure_id)).toThrow();
  });
  it("scopes GET and mutation paths to root exposure and never invokes guidance or policy endpoints", async () => {
    const transport = { request: vi.fn().mockResolvedValueOnce(data.initial).mockResolvedValueOnce(data.adjusted) };
    const api = new AdjustmentApi(transport);
    await api.read(root);
    const pending: PendingAdjustment = { kind: "view", body: { request_id: "event:" + "a".repeat(32), expected_revision: 0, parent_view_id: "original", operation: "undo", configuration: null, focus_action_id: root.pages[0].action_id } };
    await api.send(root, pending);
    expect(transport.request.mock.calls[0][0]).toContain(encodeURIComponent(root.exposure_id) + "/views");
    expect(transport.request.mock.calls[0][1]).toBe("GET");
    expect(transport.request.mock.calls[1][1]).toBe("POST");
    expect(transport.request.mock.calls.some(c => String(c[0]).endsWith("/guidance"))).toBe(false);
  });
});
describe("manual view flow and retry safety", () => {
  it("initializes through one read even under duplicate effect setup", async () => {
    const s = setup(); await Promise.all([s.flow.initialize(), s.flow.initialize()]);
    expect(s.api.read).toHaveBeenCalledTimes(1); expect(s.send).not.toHaveBeenCalled();
  });
  it("applies a distinct configuration with a stable request and does not mutate the root", async () => {
    const s = setup(); await s.flow.initialize(); const old = structuredClone(root);
    await s.flow.adjust(adjusted().spec.configuration, "adjust", root.pages[0].action_id);
    const pending = s.send.mock.calls[0][1]; expect(pending.kind).toBe("view");
    if (pending.kind === "view") { expect(pending.body.parent_view_id).toBe("original"); expect(pending.body.configuration).not.toHaveProperty("configuration_id"); }
    expect(s.flow.snapshot().value?.active_view_id).toBe(data.adjusted.active_view_id);
    expect(root).toEqual(old); expect(s.values.size).toBe(0);
  });
  it("retries an uncertain mutation unchanged and restores the pending body after reload", async () => {
    const s = setup(); await s.flow.initialize(); s.send.mockRejectedValueOnce(new Error("lost response"));
    await s.flow.adjust(adjusted().spec.configuration, "adjust", root.pages[0].action_id);
    const pending = structuredClone(s.flow.snapshot().pending);
    expect(s.flow.snapshot().ready).toBe(false); expect(s.values.size).toBe(1);
    const restored = new AdjustmentFlow(root, s.api, s.storage, "test"); await restored.initialize();
    expect(restored.snapshot().pending).toEqual(pending);
    await restored.retry(); expect(s.send.mock.calls[1][1]).toEqual(pending); expect(restored.snapshot().pending).toBeNull();
  });
  it("blocks further view changes while a request is unconfirmed", async () => {
    const s = setup(); await s.flow.initialize(); s.send.mockRejectedValue(new Error("offline"));
    await s.flow.adjust(adjusted().spec.configuration, "adjust", root.pages[0].action_id);
    await s.flow.adjust(null, "undo", root.pages[0].action_id);
    expect(s.send).toHaveBeenCalledTimes(1);
  });
  it("reloads authoritative views after stopping a local retry", async () => {
    const s = setup(); await s.flow.initialize(); s.send.mockRejectedValueOnce(new Error("409"));
    await s.flow.adjust(adjusted().spec.configuration, "adjust", root.pages[0].action_id);
    vi.mocked(s.api.read).mockResolvedValueOnce(adjusted()); await s.flow.recover();
    expect(s.flow.snapshot().value?.active_view_id).toBe(data.adjusted.active_view_id);
    expect(s.flow.snapshot().pending).toBeNull(); expect(s.values.size).toBe(0);
  });
  it("records actual manual display before accepting a manual rating", async () => {
    const s = setup(); vi.mocked(s.api.read).mockResolvedValueOnce(adjusted()); await s.flow.initialize();
    await s.flow.rate("about_right"); expect(s.send).not.toHaveBeenCalled();
    s.send.mockResolvedValueOnce(displayed()); await s.flow.visible(data.adjusted.focus_action_id);
    expect(s.send.mock.calls[0][1].kind).toBe("display");
    s.send.mockResolvedValueOnce(parseAdjustment(data.rated, root)); await s.flow.rate("about_right");
    expect(s.send.mock.calls[1][1].kind).toBe("rating"); expect(s.flow.snapshot().value?.ledger.ratings[0].learning_eligible).toBe(false);
  });
  it("does not duplicate an overview display while the action stays visible", async () => {
    const s = setup(); vi.mocked(s.api.read).mockResolvedValueOnce(displayed()); await s.flow.initialize();
    if (s.flow.snapshot().value!.spec.configuration.presentation_mode === "OVERVIEW") {
      await s.flow.visible(data.displayed.focus_action_id); expect(s.send).not.toHaveBeenCalled();
    }
  });
  it("sends Undo as its own request without a replacement configuration", async () => {
    const s = setup(); vi.mocked(s.api.read).mockResolvedValueOnce(adjusted()); await s.flow.initialize();
    s.send.mockResolvedValueOnce(parseAdjustment(data.undone, root)); await s.flow.adjust(null, "undo", root.pages[0].action_id);
    const p = s.send.mock.calls[0][1]; expect(p.kind === "view" && p.body.operation === "undo" && p.body.configuration === null).toBe(true);
    expect(s.flow.snapshot().value?.learning_eligible).toBe(false);
  });
});
describe("manual controls and honest feedback rendering", () => {
  it("renders all five controls, disabled unavailable diagram choices and explicit preference saving", async () => {
    const s = setup(); vi.mocked(s.api.read).mockResolvedValueOnce(adjusted()); await s.flow.initialize();
    const html = renderToStaticMarkup(<AdjustmentControls flow={s.flow} state={s.flow.snapshot()} disabled={false} focus={root.pages[0].action_id} onPreferencesApplied={async () => {}} />);
    for (const text of ["Hide diagram", "Overview", "Guided", "Collapse optional context", "Hide recap", "Show reminders", "Undo latest adjustment", "future preferences", "unavailable"]) expect(html).toContain(text);
  });
  it("labels manual ratings as separate from policy learning and requires display", async () => {
    const s = setup(); vi.mocked(s.api.read).mockResolvedValueOnce(adjusted()); await s.flow.initialize();
    const before = renderToStaticMarkup(<ManualViewFeedback flow={s.flow} state={s.flow.snapshot()} disabled={false} />);
    expect(before).toContain("does not train the original bandit decision"); expect(before).toContain("disabled");
    vi.mocked(s.api.read).mockResolvedValueOnce(parseAdjustment(data.rated, root)); await s.flow.refresh();
    const after = renderToStaticMarkup(<ManualViewFeedback flow={s.flow} state={s.flow.snapshot()} disabled={false} />);
    expect(after).toContain("Saved: "); expect(after).toContain("No policy update");
  });
});
