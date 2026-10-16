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