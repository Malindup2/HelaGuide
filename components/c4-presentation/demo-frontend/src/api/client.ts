import type {
  BackendHealth,
  GuestSession,
  ProcedureSummary,
} from "./types";

export const API_BASE = (
  import.meta.env.VITE_C4_API_BASE_URL ?? "http://127.0.0.1:8016"
).replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly detail: unknown = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export class ContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ContractError";
  }
}

type JsonObject = Record<string, unknown>;

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireContract(
  condition: unknown,
  message: string,
): asserts condition {
  if (!condition) {
    throw new ContractError(message);
  }
}

function isRating(value: unknown): boolean {
  return (
    value === null ||
    (typeof value === "number" &&
      Number.isInteger(value) &&
      value >= 1 &&
      value <= 5)
  );
}

function validPreferences(value: unknown): boolean {
  if (!isObject(value)) return false;

  const optionalBoolean = (item: unknown) =>
    item === null || typeof item === "boolean";

  return (
    [null, "OVERVIEW", "GUIDED"].includes(
      value.presentation_mode as null | string,
    ) &&
    optionalBoolean(value.progressive_disclosure) &&
    optionalBoolean(value.previous_context_recap) &&
    [null, "NONE", "BRANCH_MAP", "DEPENDENCY_MAP", "PARALLEL_MAP"].includes(
      value.relationship_visual as null | string,
    ) &&
    optionalBoolean(value.prerequisite_cue)
  );
}

export function parseHealth(value: unknown): BackendHealth {
  requireContract(
    isObject(value) &&
      value.service === "c4-independent-dev" &&
      value.status === "ok" &&
      typeof value.storage === "string" &&
      value.exposure_requires_acknowledgment === true,
    "The server did not return the independent C4 development API health contract.",
  );

  return value as unknown as BackendHealth;
}

export function parseProcedures(value: unknown): ProcedureSummary[] {
  requireContract(Array.isArray(value), "Invalid procedure list response.");

  const identities = new Set<string>();

  for (const item of value) {
    requireContract(
      isObject(item) &&
        typeof item.procedure_id === "string" &&
        item.procedure_id.length > 0 &&
        typeof item.plan_id === "string" &&
        typeof item.title === "string" &&
        typeof item.requested_service_id === "string" &&
        typeof item.synthetic === "boolean" &&
        (item.disclaimer === null || typeof item.disclaimer === "string") &&
        Array.isArray(item.action_ids) &&
        item.action_ids.every((id) => typeof id === "string") &&
        isObject(item.completeness) &&
        isObject(item.features),
      "A registered procedure has an unexpected response structure.",
    );

    requireContract(
      !identities.has(item.procedure_id),
      "The backend returned duplicate procedure identities.",
    );
    identities.add(item.procedure_id);
  }

  return value as ProcedureSummary[];
}

export function parseSession(value: unknown): GuestSession {
  requireContract(isObject(value), "Invalid guest-session response.");

  const settings = value.settings;

  requireContract(
    value.schema_version === "1.0" &&
      typeof value.session_id === "string" &&
      /^guest:[0-9a-f]{32}$/.test(value.session_id) &&
      typeof value.revision === "number" &&
      Number.isInteger(value.revision) &&
      value.revision >= 0 &&
      typeof value.created_at === "string" &&
      Number.isFinite(Date.parse(value.created_at)) &&
      typeof value.updated_at === "string" &&
      Number.isFinite(Date.parse(value.updated_at)) &&
      isObject(settings),
    "The backend returned an unsupported guest-session contract.",
  );

  requireContract(
    settings.schema_version === "1.0" &&
      Array.isArray(settings.familiarity) &&
      settings.familiarity.every(
        (item) =>
          isObject(item) &&
          typeof item.service_id === "string" &&
          isRating(item.score) &&
          item.source === "self_reported",
      ) &&
      isRating(settings.navigation_capability) &&
      settings.navigation_source === "self_reported" &&
      validPreferences(settings.preferences) &&
      validPreferences(settings.locks) &&
      isObject(settings.accessibility) &&
      typeof settings.accessibility.allow_relationship_visuals === "boolean" &&
      typeof settings.accessibility.allow_collapsed_content === "boolean" &&
      typeof settings.accessibility.allow_guided_navigation === "boolean",
    "The guest session contains unsupported context settings.",
  );

  return value as unknown as GuestSession;
}

function responseMessage(body: unknown, status: number): string {
  if (isObject(body)) {
    if (typeof body.detail === "string") return body.detail;

    if (isObject(body.detail) && typeof body.detail.message === "string") {
      return body.detail.message;
    }

    if (Array.isArray(body.detail)) {
      return "The backend rejected the request data.";
    }
  }

  return `The backend returned HTTP ${status}.`;
}

export class C4Api {
  constructor(
    private readonly baseUrl = API_BASE,
    private readonly fetcher: typeof fetch = globalThis.fetch.bind(globalThis),
  ) {}

  private async request(
    path: string,
    method: "GET" | "POST",
    signal?: AbortSignal,
  ): Promise<unknown> {
    let response: Response;

    try {
      response = await this.fetcher(`${this.baseUrl}${path}`, {
        method,
        signal,
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
    } catch (error) {
      if (signal?.aborted) throw error;

      throw new ApiError(
        `Cannot reach C4 at ${this.baseUrl}. Check that the development server is running and that this frontend uses port 5173.`,
        0,
      );
    }

    const text = await response.text();
    let body: unknown = null;

    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        if (!response.ok) {
          throw new ApiError(
            `The backend returned HTTP ${response.status} without a JSON error.`,
            response.status,
          );
        }

        throw new ContractError("The backend returned invalid JSON.");
      }
    }

    if (!response.ok) {
      throw new ApiError(
        responseMessage(body, response.status),
        response.status,
        body,
      );
    }

    return body;
  }

  async health(signal?: AbortSignal): Promise<BackendHealth> {
    return parseHealth(await this.request("/health", "GET", signal));
  }

  async procedures(signal?: AbortSignal): Promise<ProcedureSummary[]> {
    return parseProcedures(
      await this.request("/dev/v1/procedures", "GET", signal),
    );
  }

  async createSession(): Promise<GuestSession> {
    return parseSession(await this.request("/dev/v1/sessions", "POST"));
  }

  async getSession(
    sessionId: string,
    signal?: AbortSignal,
  ): Promise<GuestSession> {
    const session = parseSession(
      await this.request(
        `/dev/v1/sessions/${encodeURIComponent(sessionId)}`,
        "GET",
        signal,
      ),
    );

    requireContract(
      session.session_id === sessionId,
      "The backend returned a different guest-session identity.",
    );

    return session;
  }
}

export const api = new C4Api();

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "An unexpected error occurred.";
}