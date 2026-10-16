import { describe, expect, it, vi } from "vitest";
import {
  ApiError,
  C4Api,
  ContractError,
  parseHealth,
  parseProcedures,
} from "../api/client";
import type { GuestSession } from "../api/types";
import {
  resumeGuest,
  type StoragePort,
} from "../session/continuity";

const sessionId = `guest:${"a".repeat(32)}`;

function sessionFixture(): GuestSession {
  const preferences = {
    presentation_mode: null,
    progressive_disclosure: null,
    previous_context_recap: null,
    relationship_visual: null,
    prerequisite_cue: null,
  };

  return {
    schema_version: "1.0",
    session_id: sessionId,
    created_at: "2026-10-16T08:00:00Z",
    updated_at: "2026-10-16T08:00:00Z",
    revision: 0,
    settings: {
      schema_version: "1.0",
      familiarity: [],
      navigation_capability: null,
      navigation_source: "self_reported",
      preferences: { ...preferences },
      locks: { ...preferences },
      accessibility: {
        allow_relationship_visuals: true,
        allow_collapsed_content: true,
        allow_guided_navigation: true,
      },
    },
  };
}

function memoryStorage(initial?: string): StoragePort {
  const values = new Map<string, string>();
  if (initial) values.set("session", initial);

  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => {
      values.set(key, value);
    },
    removeItem: (key) => {
      values.delete(key);
    },
  };
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("backend contract boundary", () => {
  it("rejects the original team stub as the independent development API", () => {
    expect(() =>
      parseHealth({
        service: "c4-presentation",
        status: "ok",
        stub_mode: true,
      }),
    ).toThrow(ContractError);
  });

  it("preserves real procedure IDs and rejects duplicate catalogue entries", () => {
    const procedure = {
      procedure_id: "actual-backend-fingerprint",
      plan_id: "synthetic-linear-v1",
      title: "Backend-provided title",
      requested_service_id: "svc:demo_pack",
      synthetic: true,
      disclaimer: "Synthetic research example.",
      action_ids: ["action:request_token", "action:collect_pack"],
      completeness: {},
      features: {},
    };

    expect(parseProcedures([procedure])[0]).toEqual(procedure);
    expect(() => parseProcedures([procedure, procedure])).toThrow(
      ContractError,
    );
  });

  it("uses the existing session endpoint and URL-encodes its identity", async () => {
    const fetcher = vi.fn<typeof fetch>();
    fetcher.mockResolvedValue(jsonResponse(sessionFixture()));

    const client = new C4Api("http://127.0.0.1:8016", fetcher);
    const session = await client.getSession(sessionId);

    expect(session.session_id).toBe(sessionId);
    expect(fetcher).toHaveBeenCalledWith(
      `http://127.0.0.1:8016/dev/v1/sessions/${encodeURIComponent(sessionId)}`,
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("does not automatically retry failed session creation", async () => {
    const fetcher = vi.fn<typeof fetch>();
    fetcher.mockRejectedValue(new TypeError("Network failure"));

    const client = new C4Api("http://127.0.0.1:8016", fetcher);

    await expect(client.createSession()).rejects.toBeInstanceOf(ApiError);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});

describe("guest continuity", () => {
  it("resumes an existing session without creating another one", async () => {
    const expected = sessionFixture();
    const reader = {
      getSession: vi.fn().mockResolvedValue(expected),
    };
    const storage = memoryStorage(sessionId);

    const result = await resumeGuest(reader, storage, "session");

    expect(result.session).toEqual(expected);
    expect(reader.getSession).toHaveBeenCalledWith(sessionId, undefined);
    expect(storage.getItem("session")).toBe(sessionId);
  });

  it("clears a session reference only when the backend reports it missing", async () => {
    const reader = {
      getSession: vi.fn().mockRejectedValue(new ApiError("Unknown session", 404)),
    };
    const storage = memoryStorage(sessionId);

    const result = await resumeGuest(reader, storage, "session");

    expect(result.session).toBeNull();
    expect(result.notice).toContain("no longer available");
    expect(storage.getItem("session")).toBeNull();
  });

  it("preserves the saved identity during a connection failure", async () => {
    const failure = new ApiError("Cannot connect", 0);
    const reader = {
      getSession: vi.fn().mockRejectedValue(failure),
    };
    const storage = memoryStorage(sessionId);

    await expect(
      resumeGuest(reader, storage, "session"),
    ).rejects.toBe(failure);

    expect(storage.getItem("session")).toBe(sessionId);
  });
});