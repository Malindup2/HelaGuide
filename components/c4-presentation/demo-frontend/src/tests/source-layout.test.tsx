import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ActionSection, ServiceRequirements, SourceItems, SourceRegister } from "../guidance/rendering";
import { actionLabel, contentCoveredByNotice } from "../guidance/types";
import { actionNode } from "../guidance/scaffoldModel";
import { specFixture } from "./fixtures/guidance";

function legacyNoticeFirst() {
  const spec = specFixture();
  const text = "Shared procedure scope and fee exclusions.";
  spec.explanation.source.graph.disclaimer = text;
  spec.explanation.source.graph.content.unshift({ content_id: "content:scope", role: "required", text });
  for (const action of spec.explanation.source.graph.actions) action.required_content_ids.unshift("content:scope");
  for (const page of spec.pages) page.items.unshift({ kind: "content", identifier: "content:scope" });
  spec.cards.push({ source: { kind: "content", identifier: "content:scope" }, title: "Required source text", lines: [text], collapsed: false });
  const notice = spec.cards.find((card) => card.source.kind === "notice")!;
  notice.lines = [text];
  return spec;
}

describe("procedure notices and service-level requirements", () => {
  it("uses distinct instructions for legacy notice-first action and diagram labels", () => {
    const spec = legacyNoticeFirst();
    expect(actionLabel(spec, "action:one")).toBe("Required instruction 1");
    expect(actionLabel(spec, "action:two")).toBe("Required instruction 2");
    expect(actionNode(spec, "action:one").title).not.toBe(actionNode(spec, "action:two").title);
  });

  it("renders scope and service facts once while retaining every source line and original document", () => {
    const spec = legacyNoticeFirst();
    // Multi-line facts must not be truncated to their first line.
    spec.cards.find((card) => card.source.identifier === "fee:one")!.lines.push("This is the whole-service base fee.");
    const before = JSON.stringify(spec);
    const html = renderToStaticMarkup(<>
      <SourceItems doc={spec} refs={spec.global_items.filter((ref) => ref.kind === "notice")} />
      <ServiceRequirements doc={spec} />
      {spec.pages.map((page, index) => <ActionSection key={page.action_id} doc={spec} page={page} index={index}
        disabled observeToken="test" onVisible={() => {}} />)}
      <SourceRegister doc={spec} serviceFactsRendered />
    </>);
    expect(html.split("Shared procedure scope and fee exclusions.")).toHaveLength(2);
    expect(html.split("LKR 50")).toHaveLength(2);
    expect(html).toContain("not as an additional charge at each action");
    for (const card of spec.cards) for (const line of card.lines) expect(html).toContain(line);
    expect(JSON.stringify(spec)).toBe(before);
  });

  it("does not suppress protected scope when the notice is absent, collapsed or different", () => {
    for (const variant of ["absent", "collapsed", "different"]) {
      const spec = legacyNoticeFirst();
      const notice = spec.cards.find((card) => card.source.kind === "notice")!;
      if (variant === "absent") spec.global_items = spec.global_items.filter((ref) => ref.kind !== "notice");
      if (variant === "collapsed") notice.collapsed = true;
      if (variant === "different") notice.lines = ["A shorter notice."];
      expect(contentCoveredByNotice(spec, "content:scope")).toBe(false);
      const html = renderToStaticMarkup(<ActionSection doc={spec} page={spec.pages[0]} index={0} disabled observeToken="test" onVisible={() => {}} />);
      expect(html).toContain("Shared procedure scope and fee exclusions.");
    }
  });

  it("retains action-specific generated annotations even when their source is repeated in a notice", () => {
    const spec = legacyNoticeFirst();
    spec.explanation.explanations.push({ unit_id: "unit:scope", action_id: "action:one", content_id: "content:scope",
      origin: "generated", text: "Extra explanation for this action.", fact_ids: [], evidence_ids: [], citations: [] });
    const html = renderToStaticMarkup(<ActionSection doc={spec} page={spec.pages[0]} index={0} disabled observeToken="test" onVisible={() => {}} />);
    expect(html).toContain("Extra explanation for this action.");
    expect(html).toContain("Shared procedure scope and fee exclusions.");
  });
});
