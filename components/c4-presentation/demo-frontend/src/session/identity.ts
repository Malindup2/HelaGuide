import { ApiError } from "../api/client";
import type { ActiveIdentity, DemoProfileResponse, GuestSession } from "../api/types";
import {
  readStored, removeStored, resumeGuest, storageKey, writeStored,
} from "./continuity";
import type { StoragePort } from "./continuity";

interface IdentityReader {
  getProfile(profileId: string, signal?: AbortSignal): Promise<DemoProfileResponse>;
  getSession(sessionId: string, signal?: AbortSignal): Promise<GuestSession>;
}

export function rememberIdentity(
  storage: StoragePort | null,
  base: string,
  identity: ActiveIdentity,
): boolean {
  if (identity.kind === "guest") {
    const savedSession = writeStored(storage, storageKey(base, "session"), identity.session.session_id);
    const savedIdentity = writeStored(storage, storageKey(base, "identity"), JSON.stringify({ kind: "guest" }));
    return savedSession && savedIdentity;
  }
  return writeStored(
    storage, storageKey(base, "identity"),
    JSON.stringify({ kind: "profile", profile_id: identity.profile.profile_id }),
  );
}

export async function restoreIdentity(
  reader: IdentityReader,
  storage: StoragePort | null,
  base: string,
  signal?: AbortSignal,
): Promise<{ active: ActiveIdentity | null; notice: string | null }> {
  const key = storageKey(base, "identity");
  const stored = readStored(storage, key);
  if (stored) {
    let value: unknown;
    try {
      value = JSON.parse(stored);
    } catch {
      removeStored(storage, key);
      return { active: null, notice: "The saved workspace reference was invalid. Choose a profile or continue as guest." };
    }
    if (typeof value !== "object" || value === null || !("kind" in value)) {
      removeStored(storage, key);
      return { active: null, notice: "Choose a profile or continue as guest." };
    }
    if (value.kind === "profile") {
      if (!("profile_id" in value) || typeof value.profile_id !== "string" ||
          !/^profile:[0-9a-f]{32}$/.test(value.profile_id)) {
        removeStored(storage, key);
        return { active: null, notice: "The saved profile reference was invalid." };
      }
      try {
        const result = await reader.getProfile(value.profile_id, signal);
        return {
          active: { kind: "profile", ...result },
          notice: "Your saved demo profile has been restored.",
        };
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) {
          removeStored(storage, key);
          return { active: null, notice: "That demo profile is no longer available. Choose another profile or continue as guest." };
        }
        throw error;
      }
    }
    if (value.kind !== "guest") {
      removeStored(storage, key);
      return { active: null, notice: "Choose a profile or continue as guest." };
    }
  }
  // Preserve continuity from the original 7B.1 guest-only frontend.
  const result = await resumeGuest(reader, storage, storageKey(base, "session"), signal);
  return {
    active: result.session ? { kind: "guest", session: result.session } : null,
    notice: result.notice,
  };
}
