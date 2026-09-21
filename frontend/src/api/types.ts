// Mirrors contracts/schema/v1/render.schema.json
export interface RenderStep {
  order: number;
  title: string;
  body: string;
  fee_display: string;
  documents: string[];
  warning?: string | null;
}

export interface Render {
  session_id: string;
  plan_id: string;
  mode: "standard" | "simplified" | "voice";
  detail_level: "low" | "medium" | "high";
  steps: RenderStep[];
}
