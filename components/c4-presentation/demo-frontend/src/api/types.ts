export type PresentationMode = "OVERVIEW" | "GUIDED";

export type RelationshipVisual =
  | "NONE"
  | "BRANCH_MAP"
  | "DEPENDENCY_MAP"
  | "PARALLEL_MAP";

export interface PresentationPreferences {
  presentation_mode: PresentationMode | null;
  progressive_disclosure: boolean | null;
  previous_context_recap: boolean | null;
  relationship_visual: RelationshipVisual | null;
  prerequisite_cue: boolean | null;
}

export interface AccessibilityConstraints {
  allow_relationship_visuals: boolean;
  allow_collapsed_content: boolean;
  allow_guided_navigation: boolean;
}

export interface FamiliarityReport {
  service_id: string;
  score: 1 | 2 | 3 | 4 | 5 | null;
  source: "self_reported";
}

export interface UserSettings {
  schema_version: "1.0";
  familiarity: FamiliarityReport[];
  navigation_capability: 1 | 2 | 3 | 4 | 5 | null;
  navigation_source: "self_reported";
  preferences: PresentationPreferences;
  locks: PresentationPreferences;
  accessibility: AccessibilityConstraints;
}

export interface GuestSession {
  schema_version: "1.0";
  session_id: string;
  created_at: string;
  updated_at: string;
  revision: number;
  settings: UserSettings;
}

export interface BackendHealth {
  service: "c4-independent-dev";
  status: "ok";
  storage: string;
  exposure_requires_acknowledgment: true;
}

export interface ProcedureSummary {
  procedure_id: string;
  plan_id: string;
  title: string;
  requested_service_id: string;
  synthetic: boolean;
  disclaimer: string | null;
  action_ids: string[];
  completeness: Record<string, unknown>;
  features: Record<string, unknown>;
}

export type FivePointRating = 1 | 2 | 3 | 4 | 5;

export interface PersonalizationChange {
  request_id: string;
  expected_revision: number;
  enabled: boolean;
  occurred_at: string;
}

export interface DemoProfile {
  schema_version: "c4-demo-profile-1.0";
  profile_id: string;
  display_name: string;
  session_id: string;
  created_at: string;
  updated_at: string;
  revision: number;
  initial_personalization_enabled: boolean;
  personalization_enabled: boolean;
  creation_fingerprint: string;
  personalization_changes: PersonalizationChange[];
}

export interface DemoProfileResponse {
  profile: DemoProfile;
  session: GuestSession;
}

export interface CreateDemoProfileRequest {
  profile_id: string;
  display_name: string;
  personalization_enabled: boolean;
  initial_context: {
    familiarity: FamiliarityReport[];
    navigation_capability: FivePointRating | null;
    preferences: Pick<PresentationPreferences, "presentation_mode">;
    accessibility: AccessibilityConstraints;
  };
}

export interface PersonalizationRequest {
  request_id: string;
  expected_revision: number;
  enabled: boolean;
}

export type ActiveIdentity =
  | { kind: "guest"; session: GuestSession }
  | { kind: "profile"; profile: DemoProfile; session: GuestSession };
