import { ContractError } from "../api/client";
import type {
  AccessibilityConstraints, CreateDemoProfileRequest, FivePointRating,
  PresentationMode, ProcedureSummary,
} from "../api/types";

export interface ProfileDraft {
  displayName: string;
  personalizationEnabled: boolean;
  navigationCapability: FivePointRating | null;
  presentationMode: PresentationMode | null;
  familiarity: Record<string, FivePointRating | null>;
  accessibility: AccessibilityConstraints;
}

export function identifier(prefix: "profile" | "event"): string {
  return prefix + ":" + crypto.randomUUID().replaceAll("-", "");
}

export function emptyDraft(): ProfileDraft {
  return {
    displayName: "",
    personalizationEnabled: false,
    navigationCapability: null,
    presentationMode: null,
    familiarity: {},
    accessibility: {
      allow_relationship_visuals: true,
      allow_collapsed_content: true,
      allow_guided_navigation: true,
    },
  };
}

export function draftFromRequest(request: CreateDemoProfileRequest): ProfileDraft {
  return {
    displayName: request.display_name,
    personalizationEnabled: request.personalization_enabled,
    navigationCapability: request.initial_context.navigation_capability,
    presentationMode: request.initial_context.preferences.presentation_mode,
    familiarity: Object.fromEntries(
      request.initial_context.familiarity.map((entry) => [entry.service_id, entry.score]),
    ),
    accessibility: { ...request.initial_context.accessibility },
  };
}

export function buildProfileRequest(
  draft: ProfileDraft,
  procedures: ProcedureSummary[],
  profileId = identifier("profile"),
): CreateDemoProfileRequest {
  const name = draft.displayName.trim();
  if (!name || name.length > 60) {
    throw new Error("Use a demo profile label between 1 and 60 characters.");
  }
  const services = new Set(procedures.map((procedure) => procedure.requested_service_id));
  if (Object.keys(draft.familiarity).some((service) => !services.has(service))) {
    throw new Error("A selected service is no longer in the procedure catalogue.");
  }
  return parseCreationRequest({
    profile_id: profileId,
    display_name: name,
    personalization_enabled: draft.personalizationEnabled,
    initial_context: {
      navigation_capability: draft.navigationCapability,
      preferences: { presentation_mode: draft.presentationMode },
      accessibility: { ...draft.accessibility },
      familiarity: Object.entries(draft.familiarity)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([service_id, score]) => ({ service_id, score, source: "self_reported" })),
    },
  });
}

export function parseCreationRequest(value: unknown): CreateDemoProfileRequest {
  const object = (entry: unknown): entry is Record<string, unknown> =>
    typeof entry === "object" && entry !== null && !Array.isArray(entry);
  const rating = (entry: unknown) =>
    entry === null || (
      typeof entry === "number" && Number.isInteger(entry) && entry >= 1 && entry <= 5
    );
  if (!object(value) || typeof value.profile_id !== "string" ||
      !/^profile:[0-9a-f]{32}$/.test(value.profile_id) ||
      typeof value.display_name !== "string" || !value.display_name.trim() ||
      value.display_name.length > 60 ||
      typeof value.personalization_enabled !== "boolean" ||
      !object(value.initial_context)) {
    throw new ContractError("The pending profile request is invalid.");
  }
  const context = value.initial_context;
  if (!rating(context.navigation_capability) ||
      !object(context.preferences) ||
      ![null, "OVERVIEW", "GUIDED"].includes(
        context.preferences.presentation_mode as string | null,
      ) ||
      !object(context.accessibility) ||
      !["allow_relationship_visuals", "allow_collapsed_content", "allow_guided_navigation"]
        .every((key) => typeof (context.accessibility as Record<string, unknown>)[key] === "boolean") ||
      !Array.isArray(context.familiarity) ||
      !context.familiarity.every((entry) =>
        object(entry) && typeof entry.service_id === "string" &&
        rating(entry.score) && entry.source === "self_reported",
      )) {
    throw new ContractError("The pending profile context is invalid.");
  }
  const services = context.familiarity.map(
    (entry: Record<string, unknown>) => entry.service_id,
  );
  if (new Set(services).size !== services.length) {
    throw new ContractError("A pending profile contains duplicate service answers.");
  }
  return value as unknown as CreateDemoProfileRequest;
}
