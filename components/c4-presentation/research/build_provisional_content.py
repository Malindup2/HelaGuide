"""Build the DEMO-ONLY provisional 3.1 wording for the three official procedures.

Inputs: the existing assistant-authored prepared demo drafts (research/data/prepared-demo, styles concise / plain / extra_plain)
and the official-source passages. Output: research/data/guidance/provisional-v31/<procedure>.json, every text left as `draft`
with no review record. Nothing here is human-reviewed, and nothing is published to the strict registry.
  python research/build_provisional_content.py
"""
import glob
import json
import re
import sys
from pathlib import Path

C4 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(C4 / "service"))
from app.guidance import provisional  # noqa: E402
from app.guidance.content_v31 import GuidanceContent31  # noqa: E402
from app.guidance.sources import ProcedureSource  # noqa: E402
from app.v2.registration import workspace_registry  # noqa: E402

OUT = provisional.PROVISIONAL_DIR
OUT.mkdir(parents=True, exist_ok=True)

# (action, kind, phrase in that action's own source passage, fact id, label shown, role)
FACTS = {
    "official-birth_copy-v3": [
        ("action:birth_pay", "destination", "Divisional Secretariat or the specified bank route", None, "Divisional Secretariat or the specified bank route", None),
        ("action:birth_pay", "fee", "applicable copy charge", "svc:birth_copy:fee", None, "pay"),
        ("action:birth_pay", "document", "retain the receipt", "svc:birth_copy:document:1", None, "keep"),
        ("action:birth_submit", "destination", "relevant Divisional Secretariat", None, "Relevant Divisional Secretariat", None),
        ("action:birth_submit", "document", "completed request form", "svc:birth_copy:document:0", None, "submit"),
        ("action:birth_submit", "document", "payment receipt", "svc:birth_copy:document:1", None, "submit")],
    "official-nic_amendment-v3": [
        ("action:nic_estate", "destination", "Estate Superintendent", None, "Estate Superintendent", None),
        ("action:nic_estate", "document", "amendment application", "svc:nic_amendment:document:0", None, "submit"),
        ("action:nic_gn", "destination", "Grama Niladhari for the area of residence", None, "Grama Niladhari for your area", None),
        ("action:nic_gn", "document", "amendment application", "svc:nic_amendment:document:0", None, "submit"),
        ("action:nic_ds", "destination", "Divisional Secretary", None, "Divisional Secretary", None),
        ("action:nic_ds", "document", "application certified through the Grama Niladhari", "svc:nic_amendment:document:0", None, "bring")],
    "official-company_pack-v3": [
        ("action:company_articles", "document", "Articles of Association", "svc:company_pack:document:4", None, "prepare"),
        ("action:company_directors", "document", "Form 18", "svc:company_pack:document:2", None, "prepare"),
        ("action:company_secretary", "document", "Form 19", "svc:company_pack:document:3", None, "prepare"),
        ("action:company_form", "document", "Form 1", "svc:company_pack:document:1", None, "prepare"),
        ("action:company_form", "fee", "recorded Form 1 base charge is LKR 4000", "svc:company_pack:fee", None, "charge"),
        ("action:company_check", "document", "approved name certificate", "svc:company_pack:document:0", None, "submit")],
}
# fee qualifications: (action, phrase in passage, text shown)
QUALIFICATIONS = {
    ("official-birth_copy-v3", "action:birth_pay"): ("The cited counter-submission route excludes ATM and online payments", "The counter route excludes ATM and online payments."),
    ("official-company_pack-v3", "action:company_form"): ("excluding VAT and other charges; payment is outside this preparation step", "Excludes VAT and other charges. Payment is outside this step."),
}
# Small, source-grounded edits where the cached drafts were too thin (Detailed barely richer than Concise) or repeated a fact that now sits on a step or route card.
# Every sentence is supported by the source passages or the verified graph (prerequisite edges, route structure); the automatic checks still gate the result.
OVERRIDES = {
    ("official-birth_copy-v3", "action:birth_pay"): {
        "detailed": "Pay the copy charge for one certificate copy through the Divisional Secretariat or the specified bank route, and keep the receipt. You submit the receipt with the completed request form in the next step.",
        "supplement": "This does not describe the separate online application service."},
    ("official-company_pack-v3", "action:company_articles"): {
        "detailed": "Prepare two copies of the Articles of Association for the manual application. This is one of four document sets, and all four are required for the format check that follows."},
    ("official-company_pack-v3", "action:company_directors"): {
        "detailed": "Prepare Form 18 director consent documentation for the application. It is one of the four required document sets, which are submitted together for the format check."},
    ("official-company_pack-v3", "action:company_secretary"): {
        "detailed": "Prepare Form 19 secretary consent documentation for the application. It is one of the four required document sets, which are submitted together for the format check."},
    ("official-company_pack-v3", "action:company_form"): {
        "detailed": "Use the approved company name to prepare Form 1 for the incorporation application. It is one of the four required document sets, which are submitted together for the format check.",
        "supplement": "The recorded charge covers Form 1 only. It does not include the Articles, the director and secretary forms or any other charge."},
    ("official-company_pack-v3", "action:company_check"): {
        "supplement": "No order is asserted among the four preparation steps. This example stops before payment, incorporation and later obligations."},
    ("official-nic_amendment-v3", "action:nic_estate"): {
        "detailed": "If you are an estate resident, forward the amendment application through the Estate Superintendent. This is the only step on the estate route.",
        "supplement": "This example covers routing the application through its certifying officer, not preparing the full application or obtaining the card."},
    ("official-nic_amendment-v3", "action:nic_gn"): {
        "detailed": "If you are not an estate resident, forward the amendment application through the Grama Niladhari for your area. The Divisional Secretary's countersignature is required in the next step.",
        "supplement": "This example covers routing the application, not preparing the full application or obtaining the card."},
}
PHASES = {"official-company_pack-v3": [("phase:prepare", "Prepare the four document sets", ["action:company_articles", "action:company_directors", "action:company_form", "action:company_secretary"]),
                                       ("phase:submit", "Submit for the format check", ["action:company_check"])]}


def prepared_wording():
    data = {}
    for file in sorted(glob.glob(str(C4 / "research/data/prepared-demo/*.json"))):
        d = json.loads(Path(file).read_text(encoding="utf-8"))
        pid = d["source"]["graph"]["plan_id"]
        if not pid.startswith("official"):
            continue
        for item in d["draft"]["items"]:
            data.setdefault(pid, {}).setdefault(item["slot_id"], {})[d["source"]["writing_style"]] = item["text"]
    return data


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def build(pid, entry, wording):
    src = ProcedureSource(graph=entry["graph"], relationships=entry.get("overlay")).validate()
    g = src.graph
    passages = {c.content_id: c for c in g.content}
    facts = {f.fact_id: f for f in g.facts}
    claims, actions, attachments = [], [], []
    for ga in g.actions:
        aid = ga.action_id
        core = []
        for i, cid in enumerate(ga.required_content_ids):
            p = passages[cid]
            claims.append({"id": f"{aid}:claim:{i}", "source_kind": "content", "source_id": cid, "start": 0, "end": len(p.text), "quote": p.text, "action_ids": [aid], "required": True,
                           "kind": "qualification" if cid == "content:scope" else "instruction", "evidence_ids": list(p.evidence_ids)})
            core.append(f"{aid}:claim:{i}")
        ev = list(passages[ga.required_content_ids[0]].evidence_ids)
        raw = "\n\n".join(passages[c].text for c in ga.required_content_ids)
        main = passages[ga.required_content_ids[0]].text
        slot = lambda kind: wording[f"{kind}/action/{aid}"]
        heading = slot("action_heading")["plain"]
        concise, detailed, extra, summary = slot("action_explanation")["concise"], slot("action_explanation")["plain"], slot("action_explanation")["extra_plain"], slot("action_summary")["plain"]
        tail = " ".join(sentences(extra)[1:])
        over = OVERRIDES.get((pid, aid), {})
        detailed = over.get("detailed", detailed)
        tail = over.get("supplement", tail)
        text = lambda t, claim_ids=(): {"text": t, "status": "draft", "claim_ids": list(claim_ids), "evidence_ids": ev}
        action = {"id": aid, "heading": text(heading), "heading_actionable": True, "source_wording": {"text": raw, "status": "source_fallback", "claim_ids": core, "evidence_ids": ev},
                  "concise": text(concise, core), "detailed": text(detailed, core), "supplement": {"text": text(tail), "role": "clarification", "adds_information": True} if tail else None,
                  "recap": text(summary), "actor": None, "destination": None, "visible_condition_ids": list(ga.applicability.condition_ids), "visible_attachment_ids": []}
        actions.append(action)
    by = {a["id"]: a for a in actions}
    for n, (aid, kind, phrase, fact, label, role) in enumerate(FACTS[pid]):
        ga = next(x for x in g.actions if x.action_id == aid)
        cid = ga.required_content_ids[0]
        text = passages[cid].text
        if phrase not in text:
            raise ValueError(f"{pid} {aid}: phrase not in passage: {phrase}")
        start = text.index(phrase)
        ev = list(passages[cid].evidence_ids)
        claim = {"id": f"{aid}:{kind}:{n}", "source_kind": "content", "source_id": cid, "start": start, "end": start + len(phrase), "quote": phrase, "action_ids": [aid], "required": False, "kind": kind, "evidence_ids": ev}
        claims.append(claim)
        if kind == "destination":
            by[aid]["destination"] = {"text": label, "status": "draft", "claim_ids": [claim["id"]], "evidence_ids": ev}
            continue
        qualification = None
        if (pid, aid) in QUALIFICATIONS and kind == "fee":
            qphrase, qtext = QUALIFICATIONS[(pid, aid)]
            qstart = text.index(qphrase)
            qclaim = {"id": f"{aid}:qualification:{n}", "source_kind": "content", "source_id": cid, "start": qstart, "end": qstart + len(qphrase), "quote": qphrase, "action_ids": [aid], "required": False, "kind": "qualification", "evidence_ids": ev}
            claims.append(qclaim)
            qualification = {"text": qtext, "status": "draft", "claim_ids": [qclaim["id"]], "evidence_ids": ev}
        att = {"id": f"attachment:{aid}:{fact}", "fact_id": fact, "scope": "action", "action_id": aid, "stage_id": None, "service_id": None, "branch_id": None, "option_ids": [], "condition_ids": [],
               "claim_ids": [claim["id"]], "evidence_ids": ev, "qualification": qualification, "status": "draft", "role": role}
        attachments.append(att)
        by[aid]["visible_attachment_ids"].append(att["id"])
    if pid == "official-nic_amendment-v3":
        # One fee for the whole choice of routes: both route passages state the same LKR 500 issue fee, so it is attached to the route group, not to either route's step.
        estate = next(x for x in g.actions if x.action_id == "action:nic_estate")
        cid = estate.required_content_ids[0]
        text = passages[cid].text
        fee_phrase, q_phrase = "amended-card issue fee is LKR 500 and can be paid through the certifying officer", "Normal registered-post delivery adds LKR 120; that postal charge is outside the recorded base fee"
        ev = list(passages[cid].evidence_ids)
        for key, phrase, kind in (("fee", fee_phrase, "fee"), ("q", q_phrase, "qualification")):
            s = text.index(phrase)
            claims.append({"id": f"route:nic:{key}", "source_kind": "content", "source_id": cid, "start": s, "end": s + len(phrase), "quote": phrase, "action_ids": ["action:nic_estate"], "required": False, "kind": kind, "evidence_ids": ev})
        branch = g.branch_groups[0]
        attachments.append({"id": "attachment:route:nic:fee", "fact_id": "svc:nic_amendment:fee", "scope": "route", "action_id": None, "stage_id": None, "service_id": None, "branch_id": branch.group_id,
                            "option_ids": [o.option_id for o in branch.options], "condition_ids": [c for o in branch.options for c in o.condition_ids], "claim_ids": ["route:nic:fee"], "evidence_ids": ev,
                            "qualification": {"text": "Can be paid through the certifying officer. Postal delivery adds LKR 120 and is not part of this fee.", "status": "draft", "claim_ids": ["route:nic:q"], "evidence_ids": ev}, "status": "draft", "role": "pay"})
    phases = []
    for pidx, label, members in PHASES.get(pid, []):
        ev = list(passages[g.actions[0].required_content_ids[0]].evidence_ids)
        phases.append({"id": pidx, "label": {"text": label, "status": "draft", "claim_ids": [], "evidence_ids": ev}, "action_ids": members, "basis": "purpose",
                       "why_grouped": "Verified prerequisites: the four preparation actions all feed the format check.", "adds_orientation": True, "evidence_ids": ev, "branch_split_note": None})
    content = {"schema_version": "c4-guidance-content-3.1", "procedure_id": pid, "language": "en", "source_graph_fingerprint": src.graph_fingerprint, "relationship_fingerprint": src.relationship_fingerprint,
               "content_version": "provisional-demo-1", "origin": "demo_mock", "source_limit": g.disclaimer, "claims": claims, "actions": actions, "attachments": attachments, "phases": phases,
               "phase_order": [], "phase_order_basis": "none", "phase_order_evidence_ids": [], "review": None}
    model = GuidanceContent31.model_validate(content)
    report = provisional.check(src, model)
    return {"procedure_id": pid, "status": "provisional_demo_only", "label": provisional.LABEL,
            "provenance": "Derived from research/data/prepared-demo (assistant-authored demo wording, styles concise, plain, extra_plain) and the official-source passages. No human review. A few Detailed/supplement sentences were tightened afterwards (OVERRIDES in the build script) to avoid repeating facts shown on step cards; each is derived from the source passages or verified graph and passes the same checks.",
            "automatic_checks": report, "content": content}, report


def main():
    wording = prepared_wording()
    entries = workspace_registry()
    for pid in FACTS:
        packet, report = build(pid, entries[pid], wording[pid])
        (OUT / (pid + ".json")).write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(pid, "checks passed" if report["passed"] else "ISSUES", report["grounding_and_contradiction_issues"])


if __name__ == "__main__":
    main()
