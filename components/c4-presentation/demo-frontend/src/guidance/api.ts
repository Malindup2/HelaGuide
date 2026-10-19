import { api, ContractError } from "../api/client";
import type { C4Api } from "../api/client";
import { assertGuidanceScope, attachWording, parseGuidance, parseNavigation, parseSpec, parseStatus } from "./contracts";
import type { AckRequest, DisplayRequest, GuidanceRequest, Spec } from "./types";

export class GuidanceApi {
  constructor(private readonly transport: Pick<C4Api, "request"> = api) {}
  private sessionPath(id: string) { return "/dev/v1/sessions/" + encodeURIComponent(id); }
  private episodePath(spec: Spec) {
    return this.sessionPath(spec.session_id) + "/presentations/" + encodeURIComponent(spec.exposure_id);
  }
  async status(id: string) {
    const result = parseStatus(await this.transport.request(this.sessionPath(id) + "/guidance-status", "GET"));
    if (result.session_id !== id) throw new ContractError("Guidance status belongs to another session.");
    return result;
  }
  async select(id: string, request: GuidanceRequest) {
    const result = parseGuidance(await this.transport.request(this.sessionPath(id) + "/guidance", "POST", undefined, request));
    assertGuidanceScope(result, id, request.procedure_id);
    return result;
  }
  async presentation(id: string, exposureId: string, procedureId: string) {
    const response = await this.transport.request(this.sessionPath(id) + "/presentations/" + encodeURIComponent(exposureId), "GET");
    if (!response || typeof response !== "object" || !("spec" in response) || !("stale_for_display" in response)) {
      throw new ContractError("Missing saved presentation.");
    }
    const spec = attachWording(parseSpec(response.spec), "wording" in response ? response.wording : undefined);
    if (spec.session_id !== id || spec.exposure_id !== exposureId || spec.graph_fingerprint !== procedureId ||
        typeof response.stale_for_display !== "boolean") throw new ContractError("Saved presentation attribution differs.");
    return { spec, stale_for_display: response.stale_for_display };
  }
  async navigation(spec: Spec) {
    return parseNavigation(await this.transport.request(this.episodePath(spec) + "/navigation", "GET"), spec);
  }
  async acknowledge(spec: Spec, request: AckRequest) {
    // The original body is retained by the episode until the server confirms it.
    await this.transport.request(this.episodePath(spec) + "/ack", "POST", undefined, request);
  }
  async display(spec: Spec, request: DisplayRequest) {
    await this.transport.request(this.episodePath(spec) + "/navigation", "POST", undefined, request);
  }
}
export const guidanceApi = new GuidanceApi();
