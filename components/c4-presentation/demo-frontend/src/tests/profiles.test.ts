import { describe, expect, it, vi } from "vitest";
import { ApiError, C4Api, ContractError, parseProfileResponse, parseProfiles } from "../api/client";
import type {
  CreateDemoProfileRequest, DemoProfile, DemoProfileResponse, GuestSession, ProcedureSummary,
} from "../api/types";
import { buildProfileRequest, emptyDraft } from "../profiles/profileDraft";
import { rememberIdentity, restoreIdentity } from "../session/identity";
import { storageKey } from "../session/continuity";
import type { StoragePort } from "../session/continuity";

const base = "http://127.0.0.1:8016";
const profileId = "profile:" + "a".repeat(32);
const sessionId = "guest:" + "b".repeat(32);

function fixture(): DemoProfileResponse {
  const settings = {
    presentation_mode: null, progressive_disclosure: null,
    previous_context_recap: null, relationship_visual: null, prerequisite_cue: null,
  };
  const session: GuestSession = {
    schema_version: "1.0", session_id: sessionId, revision: 0,
    created_at: "2026-10-16T08:00:00Z", updated_at: "2026-10-16T08:00:00Z",
    settings: {
      schema_version: "1.0", familiarity: [], navigation_capability: null,
      navigation_source: "self_reported", preferences: { ...settings }, locks: { ...settings },
      accessibility: {
        allow_relationship_visuals: true, allow_collapsed_content: true,
        allow_guided_navigation: true,
      },
    },
  };
  const profile: DemoProfile = {
    schema_version: "c4-demo-profile-1.0", profile_id: profileId,
    display_name: "Demo A", session_id: sessionId, revision: 0,
    created_at: session.created_at, updated_at: session.created_at,
    personalization_enabled: false, initial_personalization_enabled: false,
    creation_fingerprint: "c".repeat(64), personalization_changes: [],
  };
  return { profile, session };
}

function procedures(): ProcedureSummary[] {
  return ["one", "two"].map((name) => ({
    procedure_id: name, plan_id: name, title: name, requested_service_id: "svc:" + name,
    synthetic: true, disclaimer: "Synthetic test fixture.", action_ids: [],
    completeness: {}, features: {},
  }));
}

function storage(): StoragePort {
  const items = new Map<string, string>();
  return {
    getItem: (key) => items.get(key) ?? null,
    setItem: (key, value) => { items.set(key, value); },
    removeItem: (key) => { items.delete(key); },
  };
}

function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status, headers: { "Content-Type": "application/json" },
  });
}

describe("onboarding semantics", () => {
  it("keeps skipped answers unknown, preferences soft and personalization opt-in", () => {
    const draft = emptyDraft();
    draft.displayName = "  Demo A  ";
    const request = buildProfileRequest(draft, procedures(), profileId);
    expect(request.display_name).toBe("Demo A");
    expect(request.personalization_enabled).toBe(false);
    expect(request.initial_context.navigation_capability).toBeNull();
    expect(request.initial_context.preferences.presentation_mode).toBeNull();
    expect(request.initial_context.familiarity).toEqual([]);
    expect(request.initial_context).not.toHaveProperty("locks");
  });

  it("keeps several familiarity answers scoped and never invents a medium score", () => {
    const draft = emptyDraft();
    draft.displayName = "Demo A";
    draft.personalizationEnabled = true;
    draft.presentationMode = "GUIDED";
    draft.familiarity = { "svc:two": null, "svc:one": 4 };
    draft.accessibility.allow_relationship_visuals = false;
    const request = buildProfileRequest(draft, procedures(), profileId);
    expect(request.initial_context.familiarity).toEqual([
      { service_id: "svc:one", score: 4, source: "self_reported" },
      { service_id: "svc:two", score: null, source: "self_reported" },
    ]);
    expect(request.initial_context.preferences).toEqual({ presentation_mode: "GUIDED" });
    expect(request.initial_context.accessibility.allow_relationship_visuals).toBe(false);
    expect(request.personalization_enabled).toBe(true);
    expect(request.initial_context).not.toHaveProperty("locks");
  });

  it("rejects stale service selections before sending profile creation", () => {
    const draft = emptyDraft();
    draft.displayName = "Demo";
    draft.familiarity = { "svc:missing": 3 };
    expect(() => buildProfileRequest(draft, procedures(), profileId)).toThrow("no longer");
  });
});

describe("profile contract and HTTP boundary", () => {
  it("rejects mismatched sessions, duplicate associations and inconsistent mode history", () => {
    const value = fixture();
    expect(parseProfileResponse(value)).toEqual(value);
    expect(() => parseProfileResponse({
      ...value, session: { ...value.session, session_id: "guest:" + "d".repeat(32) },
    })).toThrow(ContractError);
    expect(() => parseProfiles([value.profile, value.profile])).toThrow(ContractError);
    expect(() => parseProfiles([{ ...value.profile, personalization_enabled: true }])).toThrow(ContractError);
  });

  it("sends an explicit creation body and retries only when the caller requests it", async () => {
    const fetcher = vi.fn<typeof fetch>();
    fetcher.mockRejectedValueOnce(new TypeError("lost response"));
    fetcher.mockResolvedValueOnce(json(fixture(), 201));
    const client = new C4Api(base, fetcher);
    const draft = emptyDraft();
    draft.displayName = "Demo A";
    const request: CreateDemoProfileRequest = buildProfileRequest(draft, procedures(), profileId);

    await expect(client.createProfile(request)).rejects.toBeInstanceOf(ApiError);
    expect(fetcher).toHaveBeenCalledTimes(1);
    await client.createProfile(request);
    const first = fetcher.mock.calls[0];
    const retry = fetcher.mock.calls[1];
    expect(first[0]).toBe(base + "/dev/v1/demo-profiles");
    expect(first[1]).toMatchObject({
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    expect(retry[1]?.body).toBe(first[1]?.body);
  });

  it("preserves setting request identity and profile revision during an explicit retry", async () => {
    const value = fixture();
    const fetcher = vi.fn<typeof fetch>();
    const request = { request_id: "event:" + "e".repeat(32), expected_revision: 0, enabled: true };
    value.profile.personalization_enabled = true;
    value.profile.revision = 1;
    value.profile.personalization_changes = [{
      ...request, occurred_at: "2026-10-16T08:01:00Z",
    }];
    value.profile.updated_at = "2026-10-16T08:01:00Z";
    fetcher.mockImplementation(async () => json(value));
    const client = new C4Api(base, fetcher);
    await client.setPersonalization(profileId, request);
    await client.setPersonalization(profileId, request);
    expect(fetcher.mock.calls[0][0]).toBe(
      base + "/dev/v1/demo-profiles/" + encodeURIComponent(profileId) + "/personalization",
    );
    expect(fetcher.mock.calls[0][1]?.method).toBe("PATCH");
    expect(fetcher.mock.calls[0][1]?.body).toBe(fetcher.mock.calls[1][1]?.body);
    expect(value.session.revision).toBe(0);
  });
});

describe("guest/profile continuity", () => {
  it("restores a profile from the backend without overwriting the separate guest reference", async () => {
    const value = fixture();
    const saved = storage();
    saved.setItem(storageKey(base, "session"), "guest:" + "f".repeat(32));
    expect(rememberIdentity(saved, base, { kind: "profile", ...value })).toBe(true);
    const reader = {
      getProfile: vi.fn().mockResolvedValue(value),
      getSession: vi.fn(),
    };
    const result = await restoreIdentity(reader, saved, base);
    expect(result.active).toEqual({ kind: "profile", ...value });
    expect(reader.getProfile).toHaveBeenCalledWith(profileId, undefined);
    expect(reader.getSession).not.toHaveBeenCalled();
    expect(saved.getItem(storageKey(base, "session"))).toBe("guest:" + "f".repeat(32));
  });

  it("preserves profile identity on network failure but clears a confirmed missing profile", async () => {
    const saved = storage();
    rememberIdentity(saved, base, { kind: "profile", ...fixture() });
    const reader = {
      getProfile: vi.fn().mockRejectedValue(new ApiError("offline", 0)),
      getSession: vi.fn(),
    };
    await expect(restoreIdentity(reader, saved, base)).rejects.toBeInstanceOf(ApiError);
    expect(saved.getItem(storageKey(base, "identity"))).not.toBeNull();
    reader.getProfile.mockRejectedValueOnce(new ApiError("missing", 404));
    const result = await restoreIdentity(reader, saved, base);
    expect(result.active).toBeNull();
    expect(saved.getItem(storageKey(base, "identity"))).toBeNull();
    expect(reader.getSession).not.toHaveBeenCalled();
  });

  it("preserves the original foundation guest session when no profile was selected", async () => {
    const value = fixture();
    const saved = storage();
    saved.setItem(storageKey(base, "session"), sessionId);
    const reader = {
      getProfile: vi.fn(),
      getSession: vi.fn().mockResolvedValue(value.session),
    };
    const result = await restoreIdentity(reader, saved, base);
    expect(result.active).toEqual({ kind: "guest", session: value.session });
    expect(reader.getProfile).not.toHaveBeenCalled();
  });
});
