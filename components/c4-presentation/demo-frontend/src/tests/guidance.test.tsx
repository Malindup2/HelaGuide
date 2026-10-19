import { configuration, specFixture } from "./fixtures/guidance";
import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { C4Api, ContractError } from "../api/client";
import type { ActiveIdentity } from "../api/types";
import { GuidanceApi } from "../guidance/api";
import { parseGuidance, parseSpec } from "../guidance/contracts";
import { GuidanceEpisode, episodeStorageKey } from "../guidance/episode";
import { ActionSection, SelectedAids, SourceItems } from "../guidance/rendering";
import type { Guidance, Navigation, Standard } from "../guidance/types";
import type { StoragePort } from "../session/continuity";

const base = "http://127.0.0.1:8016";
const sid = "guest:" + "a".repeat(32);
const pid = "profile:" + "b".repeat(32);
const fp = "c".repeat(64);
function resultFixture(): Extract<Guidance, { mode: "adaptive" }> {
  return {
    mode: "adaptive", session_id: sid, session_revision: 0, profile_id: pid,
    profile_revision: 0, personalization_enabled: true, spec: specFixture(), stale_for_display: false,
  };
}
function standardFixture(): Extract<Guidance, { mode: "standard" }> {
  const spec = specFixture();
  const guidance: Standard = {
    schema_version: "c4-standard-guidance-1.0", standard_id: "standard:test",
    graph_fingerprint: fp, presentation_mode: "OVERVIEW", personalization_applied: false,
    exposure_acknowledgment_required: false, learning_eligible: false, writing_style: "plain",
    explanation: spec.explanation, cards: spec.cards, global_items: spec.global_items, pages: spec.pages,
    visibility: spec.visibility, navigation_semantics: spec.navigation_semantics,
  };
  return { mode: "standard", session_id: sid, session_revision: 0, profile_id: null, profile_revision: null, personalization_enabled: false, guidance };
}
function identity(): ActiveIdentity {
  const settings = { presentation_mode: null, progressive_disclosure: null, previous_context_recap: null, relationship_visual: null, prerequisite_cue: null };
  const session = {
    schema_version: "1.0" as const, session_id: sid, revision: 0, created_at: "2026-10-16T00:00:00Z", updated_at: "2026-10-16T00:00:00Z",
    settings: {
      schema_version: "1.0" as const, familiarity: [], navigation_capability: null, navigation_source: "self_reported" as const,
      preferences: settings, locks: settings,
      accessibility: { allow_relationship_visuals: true, allow_collapsed_content: true, allow_guided_navigation: true },
    },
  };
  return { kind: "profile", session, profile: {
    schema_version: "c4-demo-profile-1.0", profile_id: pid, display_name: "Test citizen", session_id: sid,
    created_at: session.created_at, updated_at: session.updated_at, revision: 0,
    initial_personalization_enabled: true, personalization_enabled: true, creation_fingerprint: fp, personalization_changes: [],
  } };
}
function storage(): StoragePort {
  const values = new Map<string, string>();
  return { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => { values.set(key, value); }, removeItem: (key) => { values.delete(key); } };
}
function setup() {
  const result = resultFixture();
  const api = new GuidanceApi({ request: vi.fn() });
  const status = vi.spyOn(api, "status").mockResolvedValue({
    session_id: sid, session_revision: 0, profile_id: pid, profile_revision: 0, personalization_enabled: true,
  });
  const select = vi.spyOn(api, "select").mockResolvedValue(result);
  let nav: Navigation = {
    schema_version: "c4-navigation-1.0", presentation_id: result.spec.presentation_id, exposure_id: result.spec.exposure_id,
    configuration_id: configuration.configuration_id, graph_fingerprint: fp, session_revision: 0,
    acknowledged: false, current_action_id: null, displayed_action_ids: [], events: [],
  };
  const navigation = vi.spyOn(api, "navigation").mockImplementation(async () => structuredClone(nav));
  const ack = vi.spyOn(api, "acknowledge").mockImplementation(async (_spec, request) => {
    if (!nav.acknowledged) nav = { ...nav, acknowledged: true, session_revision: 1,
      displayed_action_ids: request.displayed_action_ids, current_action_id: request.displayed_action_ids[0] };
  });
  const display = vi.spyOn(api, "display").mockImplementation(async (_spec, request) => {
    if (!nav.events.some((event) => event.event_id === request.event_id)) nav = {
      ...nav, session_revision: nav.session_revision + 1, current_action_id: request.action_id,
      displayed_action_ids: [...new Set([...nav.displayed_action_ids, request.action_id])],
      events: [...nav.events, { event_id: request.event_id, action_id: request.action_id,
        is_revisit: nav.displayed_action_ids.includes(request.action_id), sequence: nav.session_revision + 1 }],
    };
  });
  const presentation = vi.spyOn(api, "presentation").mockResolvedValue({ spec: result.spec, stale_for_display: false });
  const saved = storage();
  const episode = new GuidanceEpisode(api, identity(), fp, saved, base);
  return { result, api, episode, saved, status, select, navigation, ack, display, presentation };
}

describe("guidance contract and source rendering", () => {
  it("accepts backend standard and adaptive documents", () => {
    expect(parseGuidance(resultFixture()).mode).toBe("adaptive");
    expect(parseGuidance(standardFixture()).mode).toBe("standard");
  });
  it("rejects omitted source content and collapsed essential requirements", () => {
    const omitted = specFixture(); omitted.cards.pop();
    expect(() => parseSpec(omitted)).toThrow(ContractError);
    const collapsed = specFixture(); collapsed.cards[0].collapsed = true;
    expect(() => parseSpec(collapsed)).toThrow(ContractError);
  });
  it("rejects a mismatched selected diagram or decision identity", () => {
    const diagram = specFixture(); diagram.diagram.kind = "BRANCH_MAP";
    expect(() => parseSpec(diagram)).toThrow(ContractError);
    const decision = specFixture(); decision.decision_id = "another-decision";
    expect(() => parseSpec(decision)).toThrow(ContractError);
  });
  it("renders mandatory instructions, fees and warnings as plain text without HTML execution", () => {
    const spec = specFixture();
    spec.cards[2].lines = ["<script>not executable</script>"];
    const html = renderToStaticMarkup(<><ActionSection doc={spec} page={spec.pages[0]} index={0}
      disabled observeToken="test" onVisible={() => {}} /><SourceItems doc={spec} refs={spec.global_items} /></>);
    expect(html).toContain("&lt;script&gt;not executable&lt;/script&gt;");
    expect(html).toContain("LKR 50"); expect(html).toContain("Synthetic fixture only.");
    expect(html).not.toContain("<script>");
  });
  it("preserves XOR meanings in a selected branch aid", () => {
    const spec = specFixture();
    spec.diagram.kind = "BRANCH_MAP";
    spec.diagram.branch_groups = [{ group_id: "branch:test", service_id: "svc:demo", selection: "XOR",
      options: spec.pages.map((page, index) => ({ option_id: "option:" + index, action_ids: [page.action_id], condition_ids: [] })) }];
    const html = renderToStaticMarkup(<SelectedAids spec={spec} />);
    expect(html).toContain("Exactly one applicable option"); expect(html).toContain("does not decide eligibility");
  });
});

describe("real API boundary", () => {
  it("encodes identities and makes a single explicit selection request", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(resultFixture()), { status: 200 }));
    const api = new GuidanceApi(new C4Api(base, fetcher));
    await api.select(sid, { procedure_id: fp, expected_revision: 0, expected_profile_revision: 0, standard_writing_style: "plain" });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][0]).toBe(base + "/dev/v1/sessions/guest%3A" + "a".repeat(32) + "/guidance");
  });
  it("rejects another session's guidance", async () => {
    const result = resultFixture(); result.session_id = "guest:other"; result.spec.session_id = "guest:other";
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(result), { status: 200 }));
    await expect(new GuidanceApi(new C4Api(base, fetcher)).select(sid, {
      procedure_id: fp, expected_revision: 0, expected_profile_revision: 0, standard_writing_style: "plain",
    })).rejects.toThrow(ContractError);
  });
});

describe("stable adaptive episode", () => {
  it("selecting alone records no exposure", async () => {
    const s = setup(); await s.episode.select();
    expect(s.select).toHaveBeenCalledTimes(1);
    expect(s.ack).not.toHaveBeenCalled(); expect(s.display).not.toHaveBeenCalled();
  });
  it("records Next/Back and revisits without resampling or changing the decision", async () => {
    const s = setup(); await s.episode.select(); await s.episode.visible("action:one");
    s.episode.move("action:two"); await s.episode.visible("action:two");
    s.episode.move("action:one"); await s.episode.visible("action:one");
    expect(s.select).toHaveBeenCalledTimes(1); expect(s.ack).toHaveBeenCalledTimes(1);
    expect(s.display).toHaveBeenCalledTimes(2);
    expect(s.episode.getSnapshot().navigation?.events[1].is_revisit).toBe(true);
    const result = s.episode.getSnapshot().result;
    expect(result?.mode === "adaptive" && result.spec.decision_id).toBe(s.result.spec.decision_id);
  });
  it("ignores unknown or unfocused actions and duplicate visibility callbacks", async () => {
    const s = setup(); await s.episode.select();
    await s.episode.visible("unknown"); await s.episode.visible("action:two");
    expect(s.ack).not.toHaveBeenCalled();
    await s.episode.visible("action:one"); await s.episode.visible("action:one");
    expect(s.ack).toHaveBeenCalledTimes(1); expect(s.display).not.toHaveBeenCalled();
  });
  it("retries a lost display response with the same event and revision", async () => {
    const s = setup(); await s.episode.select(); await s.episode.visible("action:one");
    s.episode.move("action:two");
    // Mutation accepted; read-back lost. The identical mutation retry must not add another visit.
    s.navigation.mockRejectedValueOnce(new Error("connection lost"));
    await s.episode.visible("action:two");
    const pending = structuredClone(s.episode.getSnapshot().pending);
    expect(pending?.kind).toBe("navigation");
    await s.episode.retryDisplay();
    expect(s.display.mock.calls[0][1]).toEqual(s.display.mock.calls[1][1]);
    expect(s.episode.getSnapshot().navigation?.events).toHaveLength(1);
    expect(s.episode.getSnapshot().pending).toBeNull();
  });
  it("restores an episode through GETs without reselecting or creating a revisit", async () => {
    const s = setup(); await s.episode.select(); await s.episode.visible("action:one");
    s.select.mockClear(); s.ack.mockClear(); s.display.mockClear();
    const restored = new GuidanceEpisode(s.api, identity(), fp, s.saved, base);
    await restored.initialize(); await restored.initialize(); await restored.visible("action:one");
    expect(s.presentation).toHaveBeenCalledTimes(1); expect(s.select).not.toHaveBeenCalled();
    expect(s.ack).not.toHaveBeenCalled(); expect(s.display).not.toHaveBeenCalled();
  });
  it("restores the later Guided step and its history without a new display or selection", async () => {
    const s = setup();
    await s.episode.select(); await s.episode.visible("action:one");
    s.episode.move("action:two"); await s.episode.visible("action:two");
    const before = s.episode.getSnapshot();
    expect(before.restored).toBe(false);
    s.select.mockClear(); s.ack.mockClear(); s.display.mockClear();
    const restored = new GuidanceEpisode(s.api, identity(), fp, s.saved, base);
    await restored.initialize();
    expect(restored.getSnapshot().restored).toBe(true);
    expect(restored.getSnapshot().focus).toBe("action:two");
    expect(restored.getSnapshot().navigation).toEqual(before.navigation);
    await restored.visible("action:two");
    expect(s.select).not.toHaveBeenCalled(); expect(s.ack).not.toHaveBeenCalled();
    expect(s.display).not.toHaveBeenCalled();
    await restored.select();
    expect(restored.getSnapshot().restored).toBe(false);
  });
  it("retains an unconfirmed initial acknowledgment across reload and retries it unchanged", async () => {
    const s = setup(); await s.episode.select();
    s.ack.mockRejectedValueOnce(new Error("lost response"));
    await s.episode.visible("action:one");
    const original = s.episode.getSnapshot().pending;
    const restored = new GuidanceEpisode(s.api, identity(), fp, s.saved, base);
    await restored.initialize();
    expect(restored.getSnapshot().pending).toEqual(original);
    await restored.retryDisplay();
    expect(s.ack.mock.calls[0][1]).toEqual(s.ack.mock.calls[1][1]);
  });
  it("does not send display mutations for standard guest guidance", async () => {
    const s = setup(); const active = identity();
    s.status.mockResolvedValue({ session_id: sid, session_revision: 0, profile_id: null, profile_revision: null, personalization_enabled: false });
    s.select.mockResolvedValue(standardFixture());
    const guest = new GuidanceEpisode(s.api, { kind: "guest", session: active.session }, fp, s.saved, base);
    await guest.select(); await guest.visible("action:one");
    expect(s.ack).not.toHaveBeenCalled(); expect(s.display).not.toHaveBeenCalled();
  });
  it("restores an acknowledged stale presentation for feedback without new display events", async () => {
    const s = setup(); await s.episode.select(); await s.episode.visible("action:one");
    s.presentation.mockResolvedValue({ spec: s.result.spec, stale_for_display: true });
    s.select.mockClear(); s.ack.mockClear(); s.display.mockClear();
    const restored = new GuidanceEpisode(s.api, identity(), fp, s.saved, base);
    await restored.initialize();
    restored.move("action:two"); await restored.visible("action:two");
    const result = restored.getSnapshot().result;
    expect(result?.mode === "adaptive" && result.stale_for_display).toBe(true);
    expect(result?.mode === "adaptive" && result.spec.decision_id).toBe(s.result.spec.decision_id);
    expect(restored.getSnapshot().focus).toBe("action:one");
    expect(s.select).not.toHaveBeenCalled(); expect(s.ack).not.toHaveBeenCalled(); expect(s.display).not.toHaveBeenCalled();
  });
  it("fails closed on stale saved episodes and separates sessions/procedures/profile revisions", async () => {
    const s = setup(); await s.episode.select();
    s.presentation.mockResolvedValue({ spec: s.result.spec, stale_for_display: true });
    const restored = new GuidanceEpisode(s.api, identity(), fp, s.saved, base);
    await restored.initialize();
    expect(restored.getSnapshot().result).toBeNull(); expect(s.ack).not.toHaveBeenCalled();
    expect(episodeStorageKey(base, identity(), fp)).not.toBe(episodeStorageKey(base, identity(), "other"));
    const other = identity(); other.session.session_id = "guest:other";
    expect(episodeStorageKey(base, identity(), fp)).not.toBe(episodeStorageKey(base, other, fp));
  });

  it("records only visible Overview actions and never assumes the whole document was viewed", async () => {
    const s = setup();
    const spec = s.result.spec;
    spec.configuration.presentation_mode = "OVERVIEW";
    spec.configuration.configuration_id = "c4-scaffold-v1:OVERVIEW:pd0:recap0:NONE:cue0";
    spec.initial_action_id = null;
    spec.acknowledgment_action_ids = spec.pages.map((page) => page.action_id);
    await s.episode.select(); await s.episode.visible("action:two");
    expect(s.ack.mock.calls[0][1].displayed_action_ids).toEqual(["action:two"]);
    expect(s.episode.getSnapshot().navigation?.displayed_action_ids).toEqual(["action:two"]);
    await s.episode.visible("action:one");
    expect(s.select).toHaveBeenCalledTimes(1); expect(s.display).toHaveBeenCalledTimes(1);
  });
  it("does not create a new selection if consent changed elsewhere", async () => {
    const s = setup();
    s.status.mockResolvedValue({ session_id: sid, session_revision: 0, profile_id: pid, profile_revision: 1, personalization_enabled: false });
    await s.episode.select();
    expect(s.select).not.toHaveBeenCalled();
    expect(s.episode.getSnapshot().error).toContain("Profile settings changed");
  });
  it("closing an uncertain episode does not invent a reward or undo accepted history", async () => {
    const s = setup(); await s.episode.select();
    s.ack.mockRejectedValueOnce(new Error("connection lost"));
    await s.episode.visible("action:one");
    s.episode.close();
    expect(s.episode.getSnapshot().pending).toBeNull();
    expect(s.episode.getSnapshot().result).toBeNull();
    expect(s.saved.getItem(episodeStorageKey(base, identity(), fp))).toBeNull();
    expect(s.select).toHaveBeenCalledTimes(1);
  });
});
