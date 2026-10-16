import { ApiError } from "../api/client";
import type { GuestSession } from "../api/types";

export interface StoragePort {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

interface SessionReader {
  getSession(sessionId: string, signal?: AbortSignal): Promise<GuestSession>;
}

export interface ResumeResult {
  session: GuestSession | null;
  notice: string | null;
}

export function storageKey(
  apiBase: string,
  kind: "session" | "procedure",
): string {
  return `helaguide:c4:v1:${apiBase}:${kind}`;
}

export function browserStorage(): StoragePort | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function readStored(
  storage: StoragePort | null,
  key: string,
): string | null {
  try {
    return storage?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

export function writeStored(
  storage: StoragePort | null,
  key: string,
  value: string,
): boolean {
  if (!storage) return false;

  try {
    storage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

function removeStored(storage: StoragePort | null, key: string): void {
  try {
    storage?.removeItem(key);
  } catch {
    // Storage availability must not prevent normal in-memory operation.
  }
}

export async function resumeGuest(
  reader: SessionReader,
  storage: StoragePort | null,
  key: string,
  signal?: AbortSignal,
): Promise<ResumeResult> {
  const sessionId = readStored(storage, key);

  if (!sessionId) {
    return { session: null, notice: null };
  }

  if (!/^guest:[0-9a-f]{32}$/.test(sessionId)) {
    removeStored(storage, key);
    return {
      session: null,
      notice: "The saved session reference was invalid. Start a new guest session.",
    };
  }

  try {
    return {
      session: await reader.getSession(sessionId, signal),
      notice: "Your guest session has been restored.",
    };
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      removeStored(storage, key);
      return {
        session: null,
        notice:
          "The saved guest session is no longer available in this backend. You can start a new one.",
      };
    }

    throw error;
  }
}