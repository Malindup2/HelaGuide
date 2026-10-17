import { describe, expect, it, vi } from "vitest";
import { ApiError, C4Api, ContractError } from "../api/client";
import { FeedbackApi } from "../feedback/api";
import { parseAccepted, parseCorrection, parseOptions, parsePolicy } from "../feedback/contracts";
import { FeedbackFlow, feedbackStorageKey } from "../feedback/flow";
import { correctionValues } from "../feedback/types";
import type { AcceptedFeedback, CorrectionOptions, CorrectionRecord, PolicyStatus, Rating } from "../feedback/types";
import type { GuestSession } from "../api/types";
import type { Navigation } from "../guidance/types";
import type { StoragePort } from "../session/continuity";
import { specFixture } from "./fixtures/guidance";
const base = "http://127.0.0.1:8016";
function policyFixture(): PolicyStatus {
  return { policy_run_id: "policy:test", model_version: "c4-shared-lints-1.0", feedback_mode: "simulation",
    feature_schema_version: "c4-context-action-1.0", feature_schema_fingerprint: "a".repeat(64), feature_dimension: 656,
    posterior_revision: 0, posterior_fingerprint: "b".repeat(64), accepted_feedback_count: 0, storage: "postgresql" };
}
function receipt(rating: Rating = "need_more"): AcceptedFeedback {
  const spec = specFixture();
  return { accepted_at: "2026-10-16T08:00:00Z", receipt: {
    feedback: { exposure_id: spec.exposure_id, rating, origin: "simulation" }, policy_run_id: "policy:test",
    decision_id: spec.decision_id, acknowledgment_event_id: "event:" + "1".repeat(32),
    reward: rating === "about_right" ? 1 : 0, procedure_synthetic: true,
    selection_posterior_revision: 0, resulting_posterior_revision: 1,
  } };
}
function sessionFixture(): GuestSession {
  const preferences = { presentation_mode: null, progressive_disclosure: null, previous_context_recap: null, relationship_visual: null, prerequisite_cue: null };
  return {
    schema_version: "1.0", session_id: specFixture().session_id, revision: 1,
    created_at: "2026-10-16T07:00:00Z", updated_at: "2026-10-16T08:00:00Z",
    settings: { schema_version: "1.0", familiarity: [], navigation_capability: null, navigation_source: "self_reported",
      preferences: { ...preferences }, locks: { ...preferences },
      accessibility: { allow_relationship_visuals: true, allow_collapsed_content: true, allow_guided_navigation: true } },
  };
}
function storage(): StoragePort {
  const values = new Map<string, string>();
  return { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => { values.set(key, value); }, removeItem: (key) => { values.delete(key); } };
}
function setup() {
  const spec = specFixture(); const saved = storage();
  const api = new FeedbackApi({ request: vi.fn() });
  let accepted: AcceptedFeedback | null = null; let correction: CorrectionRecord | null = null;
  let policy = policyFixture(); let session = sessionFixture();
  const optionsFixture = (): CorrectionOptions => ({
    session_revision: session.revision, feedback_eligible: !!accepted && accepted.receipt.feedback.rating !== "about_right",
    choices: Object.entries(correctionValues).map(([code, [dimension, value]]) => ({
      code: code as keyof typeof correctionValues, label: code, dimension, value,
      selected_in_original: spec.configuration[dimension as keyof typeof spec.configuration] === value,
      available_for_future: code !== "show_branch_map", unavailable_reason: code === "show_branch_map" ? "No branch structure." : null,
    })),
  });
  const policyRead = vi.spyOn(api, "policy").mockImplementation(async () => structuredClone(policy));
  vi.spyOn(api, "decision").mockResolvedValue({
    decision_id: spec.decision_id, policy_run_id: policy.policy_run_id, posterior_revision: 0,
    selection_mode: "cold_start_baseline", feature_dimension: 656,
    feature_schema_version: policy.feature_schema_version, feature_schema_fingerprint: policy.feature_schema_fingerprint,
  });
  const acceptedRead = vi.spyOn(api, "accepted").mockImplementation(async () => structuredClone(accepted));
  vi.spyOn(api, "correction").mockImplementation(async () => structuredClone(correction));
  const options = vi.spyOn(api, "options").mockImplementation(async () => optionsFixture());
  const rate = vi.spyOn(api, "rate").mockImplementation(async (_spec, request) => {
    if (accepted && accepted.receipt.feedback.rating !== request.rating) throw new ApiError("conflicting rating", 409);
    if (!accepted) {
      accepted = receipt(request.rating);
      policy = { ...policy, posterior_revision: 1, posterior_fingerprint: "c".repeat(64), accepted_feedback_count: 1 };
    }
    return structuredClone(accepted);
  });
  const record = vi.spyOn(api, "record").mockImplementation(async (_spec, feedback, request) => {
    correction ??= { ...request, reasons: [...request.reasons].sort(),
      schema_version: "c4-correction-1.0", session_id: spec.session_id, exposure_id: spec.exposure_id,
      graph_fingerprint: spec.graph_fingerprint, rating: feedback.receipt.feedback.rating as "need_more" | "too_much",
      origin: feedback.receipt.feedback.origin, acknowledgment_event_id: feedback.receipt.acknowledgment_event_id,
      feedback_posterior_revision: feedback.receipt.resulting_posterior_revision,
      recorded_at: "2026-10-16T08:01:00Z", application: null };
    return structuredClone(correction);
  });
  const apply = vi.spyOn(api, "apply").mockImplementation(async (_spec, _feedback, request) => {
    if (!correction) throw new ApiError("no correction", 404);
    if (!correction.application) {
      if (session.revision !== request.expected_revision) throw new ApiError("session revision changed", 409);
      const before = structuredClone(session);
      session = structuredClone(session);
      for (const code of correction.reasons) {
        const [dimension, value] = correctionValues[code];
        Object.assign(session.settings.preferences, { [dimension]: value });
      }
      session.revision += 1;
      correction.application = { expected_revision: request.expected_revision, applied_at: "2026-10-16T08:02:00Z",
        before, after: structuredClone(session), preference_event_id: "event:" + "2".repeat(32) };
    }
    return structuredClone(correction);
  });
  const navigation: Navigation = {
    schema_version: "c4-navigation-1.0", presentation_id: spec.presentation_id, exposure_id: spec.exposure_id,
    configuration_id: spec.configuration.configuration_id, graph_fingerprint: spec.graph_fingerprint,
    session_revision: 1, acknowledged: true, current_action_id: "action:one", displayed_action_ids: ["action:one"], events: [],
  };
  const flow = new FeedbackFlow(api, spec, saved, base);
  return { api, flow, spec, saved, navigation, rate, record, apply, options, acceptedRead, policyRead, optionsFixture,
    setAccepted: (value: AcceptedFeedback) => { accepted = value; policy = { ...policy, posterior_revision: 1, accepted_feedback_count: 1 }; } };
}

describe("feedback API contracts", () => {
  it("rejects wrong exposure attribution and incorrect reward mappings", () => {
    const spec = specFixture(); const wrong = receipt(); wrong.receipt.feedback.exposure_id = "exposure:other";
    expect(() => parseAccepted(wrong, spec)).toThrow(ContractError);
    const reward = receipt("need_more"); reward.receipt.reward = 1;
    expect(() => parseAccepted(reward, spec)).toThrow(ContractError);
  });
  it("preserves simulation origin and rejects an incompatible feature dimension", () => {
    expect(parseAccepted(receipt(), specFixture()).receipt.feedback.origin).toBe("simulation");
    expect(() => parsePolicy({ ...policyFixture(), feature_dimension: 64 })).toThrow(ContractError);
  });
  it("uses backend availability and rejects incorrect correction mappings", () => {
    const s = setup(); const options = s.optionsFixture();
    expect(parseOptions(options, s.spec).choices.find((choice) => choice.code === "show_branch_map")?.available_for_future).toBe(false);
    options.choices[0].value = "GUIDED";
    expect(() => parseOptions(options, s.spec)).toThrow(ContractError);
  });
  it("posts exactly one rating request with encoded attribution and no automatic retry", async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error("lost connection"));
    const api = new FeedbackApi(new C4Api(base, fetcher)); const spec = specFixture();
    await expect(api.rate(spec, { presentation_id: spec.presentation_id, configuration_id: spec.configuration.configuration_id,
      decision_id: spec.decision_id, rating: "about_right" })).rejects.toThrow();
    expect(fetcher).toHaveBeenCalledTimes(1); expect(fetcher.mock.calls[0][0]).toContain("guest%3A");
  });
});

describe("explicit feedback workflow", () => {
  it("initializes through reads without producing rewards, corrections or preference changes", async () => {
    const s = setup(); await s.flow.initialize(); await s.flow.initialize();
    expect(s.rate).not.toHaveBeenCalled(); expect(s.record).not.toHaveBeenCalled(); expect(s.apply).not.toHaveBeenCalled();
    expect(s.acceptedRead).toHaveBeenCalledTimes(1);
  });
  it("refuses feedback before acknowledgment or for another exposure", async () => {
    const s = setup(); await s.flow.initialize();
    await s.flow.rate("about_right", { ...s.navigation, acknowledged: false });
    await s.flow.rate("about_right", { ...s.navigation, exposure_id: "another" });
    expect(s.rate).not.toHaveBeenCalled();
  });
  it("submits one explicit rating and displays the actual accepted revision and updated fingerprint", async () => {
    const s = setup(); await s.flow.initialize(); await s.flow.rate("about_right", s.navigation);
    expect(s.rate).toHaveBeenCalledTimes(1);
    expect(s.flow.getSnapshot().accepted?.receipt.reward).toBe(1);
    expect(s.flow.getSnapshot().accepted?.receipt.resulting_posterior_revision).toBe(1);
    expect(s.flow.getSnapshot().before?.posterior_fingerprint).not.toBe(s.flow.getSnapshot().policy?.posterior_fingerprint);
    await s.flow.rate("too_much", s.navigation); expect(s.rate).toHaveBeenCalledTimes(1);
  });
  it("retries the same rating after a lost read-back without a second accepted update", async () => {
    const s = setup(); await s.flow.initialize();
    s.acceptedRead.mockRejectedValueOnce(new Error("lost read-back"));
    await s.flow.rate("need_more", s.navigation);
    expect(s.flow.getSnapshot().pending?.kind).toBe("rating");
    await s.flow.retry();
    expect(s.rate.mock.calls[0][1]).toEqual(s.rate.mock.calls[1][1]);
    expect(s.flow.getSnapshot().policy?.accepted_feedback_count).toBe(1);
  });
  it("recovers accepted feedback after reload without automatically posting again", async () => {
    const s = setup(); await s.flow.initialize();
    s.acceptedRead.mockRejectedValueOnce(new Error("lost read-back"));
    await s.flow.rate("need_more", s.navigation); s.rate.mockClear();
    const restored = new FeedbackFlow(s.api, s.spec, s.saved, base); await restored.initialize();
    expect(restored.getSnapshot().accepted?.receipt.feedback.rating).toBe("need_more");
    expect(restored.getSnapshot().pending).toBeNull(); expect(s.rate).not.toHaveBeenCalled();
  });
  it("keeps an unconfirmed original request when recovery reads return incompatible policy records", async () => {
    const s = setup(); await s.flow.initialize();
    s.rate.mockRejectedValueOnce(new Error("offline"));
    await s.flow.rate("need_more", s.navigation);
    const pending = structuredClone(s.flow.getSnapshot().pending);
    s.policyRead.mockRejectedValueOnce(new ContractError("incompatible policy"));
    const restored = new FeedbackFlow(s.api, s.spec, s.saved, base);
    await restored.initialize();
    expect(restored.getSnapshot().pending).toEqual(pending);
    expect(restored.getSnapshot().ready).toBe(false);
    expect(s.saved.getItem(feedbackStorageKey(base, s.spec))).not.toBeNull();
    await restored.refresh();
    expect(restored.getSnapshot().pending).toEqual(pending);
    expect(s.rate).toHaveBeenCalledTimes(1);
  });
  it("retains the backend's conflicting rating rather than replacing it", async () => {
    const s = setup(); await s.flow.initialize(); s.setAccepted(receipt("about_right"));
    await s.flow.rate("too_much", s.navigation);
    expect(s.flow.getSnapshot().accepted?.receipt.feedback.rating).toBe("about_right");
    expect(s.flow.getSnapshot().error).toContain("conflicting rating");
    expect(s.flow.getSnapshot().pending).toBeNull();
  });
  it("saves optional diagnostic reasons without automatically applying preferences or another reward", async () => {
    const s = setup(); await s.flow.initialize(); await s.flow.rate("need_more", s.navigation);
    await s.flow.record(["prefer_overview", "hide_diagram"]);
    expect(s.flow.getSnapshot().correction?.reasons).toEqual(["hide_diagram", "prefer_overview"]);
    expect(s.apply).not.toHaveBeenCalled(); expect(s.rate).toHaveBeenCalledTimes(1);
    await s.flow.record(["prefer_guided"]); expect(s.record).toHaveBeenCalledTimes(1);
  });
  it("does not accept contradictory reasons for the same scaffold dimension", async () => {
    const s = setup(); await s.flow.initialize(); await s.flow.rate("need_more", s.navigation);
    await s.flow.record(["prefer_guided", "prefer_overview"]);
    expect(s.record).not.toHaveBeenCalled();
  });
  it("applies recorded choices only explicitly, preserves hard settings and keeps learning attribution", async () => {
    const s = setup(); await s.flow.initialize(); await s.flow.rate("need_more", s.navigation);
    await s.flow.record(["prefer_overview"]); await s.flow.apply();
    const state = s.flow.getSnapshot(); const application = state.correction!.application!;
    expect(application.after.settings.preferences.presentation_mode).toBe("OVERVIEW");
    expect(application.after.settings.locks).toEqual(application.before.settings.locks);
    expect(application.after.settings.accessibility).toEqual(application.before.settings.accessibility);
    expect(state.policy?.posterior_revision).toBe(1); expect(s.rate).toHaveBeenCalledTimes(1);
    expect(parseCorrection(state.correction, s.spec, state.accepted!)).toEqual(state.correction);
  });
  it("retains an identical preference-application revision for retries", async () => {
    const s = setup(); await s.flow.initialize(); await s.flow.rate("too_much", s.navigation);
    await s.flow.record(["prefer_overview"]);
    s.acceptedRead.mockRejectedValueOnce(new Error("read-back failed"));
    await s.flow.apply(); expect(s.flow.getSnapshot().pending?.kind).toBe("apply");
    await s.flow.retry();
    expect(s.apply.mock.calls[0][2]).toEqual(s.apply.mock.calls[1][2]);
    expect(s.flow.getSnapshot().correction?.application?.after.revision).toBe(2);
  });
  it("does not silently retry an application against a different context revision", async () => {
    const s = setup(); await s.flow.initialize(); await s.flow.rate("need_more", s.navigation); await s.flow.record(["prefer_overview"]);
    s.apply.mockRejectedValueOnce(new ApiError("session revision changed", 409));
    await s.flow.apply();
    expect(s.apply).toHaveBeenCalledTimes(1); expect(s.flow.getSnapshot().pending).toBeNull();
    expect(s.flow.getSnapshot().error).toContain("session revision changed");
  });
  it("separates pending requests by session, exposure and decision and can stop a local retry", async () => {
    const s = setup(); await s.flow.initialize(); s.rate.mockRejectedValueOnce(new Error("offline"));
    await s.flow.rate("need_more", s.navigation);
    const other = specFixture(); other.exposure_id = "exposure:other";
    expect(feedbackStorageKey(base, s.spec)).not.toBe(feedbackStorageKey(base, other));
    s.flow.stopRetrying(); expect(s.flow.getSnapshot().pending).toBeNull();
    expect(s.flow.getSnapshot().ready).toBe(false); expect(s.flow.getSnapshot().notice).toContain("server may already");
  });
});
