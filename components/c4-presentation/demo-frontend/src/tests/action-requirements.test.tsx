import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { specFixture } from "./fixtures/guidance";
import { actionFactItems } from "../guidance/types";
import { ActionSection, ServiceRequirements } from "../guidance/rendering";
import { attachWording, parseSpec } from "../guidance/contracts";

describe("action-specific preparation", () => {
  it("places a fee only on the explicitly linked step and keeps service-only fees separate", () => {
    const spec = specFixture();
    spec.explanation.source.graph.content[0].fact_ids = ["fee:one"];
    const before = JSON.stringify(spec);
    expect(actionFactItems(spec, "action:one")).toEqual([{kind:"fact", identifier:"fee:one"}]);
    expect(actionFactItems(spec, "action:two")).toEqual([]);
    const render = (index: number) => renderToStaticMarkup(<ActionSection doc={spec} page={spec.pages[index]}
      index={index} disabled observeToken="test" onVisible={() => {}} />);
    expect(render(0)).toContain("LKR 50");
    expect(render(1)).not.toContain("LKR 50");
    expect(renderToStaticMarkup(<ServiceRequirements doc={spec} />)).not.toContain("LKR 50");
    expect(render(1)).toContain("does not mean the step is free");
    expect(JSON.stringify(spec)).toBe(before);
  });
  it("does not treat procedure scope as an action requirement", () => {
    const spec = specFixture();
    spec.explanation.source.graph.content[0].text = spec.explanation.source.graph.disclaimer;
    spec.explanation.source.graph.content[0].fact_ids = ["fee:one"];
    expect(actionFactItems(spec, "action:one")).toEqual([]);
    expect(renderToStaticMarkup(<ServiceRequirements doc={spec} />)).toContain("LKR 50");
  });
  it("rejects missing fact references rather than silently omitting requirements", () => {
    const spec = specFixture();
    spec.explanation.source.graph.content[0].fact_ids = ["unknown"];
    expect(() => parseSpec(spec)).toThrow("unknown action content fact");
  });
  it("renders stored mock headings and explanations without source truncation or mutation", () => {
    const spec=specFixture();
    const before=JSON.stringify(spec);
    const prepared={request_key:"a".repeat(64), graph_fingerprint:spec.graph_fingerprint,
      artifact_digest:"b".repeat(64), diagnostics:["demo_mock_not_expert_reviewed_or_live_provider_output"],
      items:[{slot_id:"action_heading/action/action:one",text:"Prepare your application",origin:"demo_mock",
        source_references:[{kind:"action",reference_id:"action:one"}]},
      {slot_id:"action_explanation/action/action:one",text:"A stored explanation of this step.",origin:"demo_mock",
        source_references:[{kind:"action",reference_id:"action:one"}]}]};
    const doc=attachWording(spec,prepared);
    const html=renderToStaticMarkup(<ActionSection doc={doc} page={doc.pages[0]} index={0} disabled observeToken="test" onVisible={() => {}} />);
    expect(html).toContain("Prepare your application");
    expect(html).toContain("A stored explanation of this step.");
    expect(html).toContain("Required instruction 1");
    expect(JSON.stringify(spec)).toBe(before);
  });
});
