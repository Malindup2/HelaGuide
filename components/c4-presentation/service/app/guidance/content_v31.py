"""Candidate prepared-content contract c4-guidance-content-3.1. NOT wired into the runtime, registry, policy or checkpoint.

It separates three things that 3.0 folds together:
  * a short reviewed primary explanation per depth (`concise`, `detailed`), each complete on its own;
  * the exact source wording (`source_wording`), always kept with the action;
  * one separate nonessential `supplement`, the only thing Progressive Disclosure may hide.
Shared checks (claims, attachments, phases, fee scope) are delegated to the 3.0 validator through a derived 3.0 view,
so that logic is not duplicated. Coverage proves explicit assignment of claim ids, not semantic entailment.
"""
from typing import Literal
from pydantic import Field, model_validator
from app.guidance.catalogue import CATALOGUE, Constraints
from app.guidance.content import (Action, Attachment, Claim, Explanation, GuidanceContent, Phase, Record, Review, Text, validate_content)
from app.guidance.feasibility import Candidate
from app.guidance.sources import ProcedureSource, digest

SCHEMA31 = "c4-guidance-content-3.1"
INSTRUCTION_KINDS = ("instruction", "condition", "qualification")


class Supplement(Record):
    text: Text
    role: Literal["clarification", "qualification", "background"]
    adds_information: bool = False


class Attachment31(Attachment):
    """3.0 attachment plus what the citizen does with the fact at this step (shown as Bring, Prepare, Submit, Keep, Pay or Charge)."""
    role: Literal["bring", "prepare", "submit", "keep", "pay", "charge"] = "bring"


class Action31(Record):
    id: str
    heading: Text
    heading_actionable: bool = False
    source_wording: Text
    concise: Text
    detailed: Text | None = None
    supplement: Supplement | None = None
    recap: Text | None = None
    actor: Text | None = None
    destination: Text | None = None
    visible_condition_ids: tuple[str, ...] = ()
    visible_attachment_ids: tuple[str, ...] = ()


class GuidanceContent31(Record):
    schema_version: Literal["c4-guidance-content-3.1"] = SCHEMA31
    procedure_id: str
    language: str = Field(default="en", pattern=r"^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
    source_graph_fingerprint: str
    relationship_fingerprint: str
    content_version: str = Field(min_length=1)
    origin: Literal["fictional_authored", "human_prepared", "provider_generated", "source_preserving", "demo_mock"]
    source_limit: str
    claims: tuple[Claim, ...]
    actions: tuple[Action31, ...]
    attachments: tuple[Attachment31, ...] = ()
    phases: tuple[Phase, ...] = ()
    phase_order: tuple[str, ...] = ()
    phase_order_basis: Literal["none", "stage_edges", "reviewed_overlay"] = "none"
    phase_order_evidence_ids: tuple[str, ...] = ()
    review: Review | None = None

    @property
    def fingerprint(self):
        return digest(self.model_dump(mode="json", exclude={"review"}))


def to_v30(content: GuidanceContent31) -> GuidanceContent:
    """3.0 view used only to reuse the shared validator: source wording plays the 3.0 'essential' role."""
    actions = tuple(Action(id=a.id, heading=a.heading, heading_actionable=a.heading_actionable, essential=a.source_wording,
                           concise=Explanation(status="source_fallback"), detailed=None, recap=a.recap, actor=a.actor, destination=a.destination,
                           visible_condition_ids=a.visible_condition_ids, visible_attachment_ids=a.visible_attachment_ids) for a in content.actions)
    plain = GuidanceContent(procedure_id=content.procedure_id, language=content.language, source_graph_fingerprint=content.source_graph_fingerprint,
                            relationship_fingerprint=content.relationship_fingerprint, content_version=content.content_version, origin=content.origin,
                            source_limit=content.source_limit, claims=content.claims, actions=actions, attachments=tuple(Attachment.model_validate(a.model_dump(exclude={"role"})) for a in content.attachments), phases=content.phases,
                            phase_order=content.phase_order, phase_order_basis=content.phase_order_basis, phase_order_evidence_ids=content.phase_order_evidence_ids)
    if content.review is None:
        return plain
    return plain.model_copy(update={"review": content.review.model_copy(update={"artifact_digest": plain.fingerprint})})


def validate_content31(source: ProcedureSource, content: GuidanceContent31) -> GuidanceContent31:
    reviewed = bool(content.review and content.review.status == "reviewed")
    if reviewed and content.review.artifact_digest != content.fingerprint:
        raise ValueError("review digest does not match 3.1 content")
    validate_content(source, to_v30(content))
    g = source.graph
    claims = {c.id: c for c in content.claims}
    evidence = {e.evidence_id for e in g.evidence}
    checks = {c.target: c for c in content.review.checks} if content.review else {}

    def check_text(field, target):
        if not set(field.claim_ids) <= claims.keys() or not set(field.evidence_ids) <= evidence:
            raise ValueError("unresolved text references")
        if field.status == "reviewed":
            c = checks.get(target)
            if not reviewed or c is None or c.result != "matched" or not set(field.claim_ids) <= set(c.claim_ids) or not field.evidence_ids or not set(field.evidence_ids) <= set(c.evidence_ids):
                raise ValueError("missing named source-fidelity review: " + target)

    for a in content.actions:
        prefix = "actions." + a.id
        required = [c for c in content.claims if c.required and a.id in c.action_ids]
        core = {c.id for c in required if c.kind in INSTRUCTION_KINDS}
        for name, field in (("concise", a.concise), ("detailed", a.detailed)):
            if field is None:
                continue
            check_text(field, prefix + "." + name)
            if any(a.id not in claims[k].action_ids for k in field.claim_ids):
                raise ValueError("text uses another action's claim")
            if field.status != "draft" and not core <= set(field.claim_ids):
                raise ValueError(name + " must carry every required instruction, condition and qualification of its action")
            if field.text.strip() == a.heading.text.strip():
                raise ValueError(name + " must say more than the heading")
        if a.detailed is not None:
            if not set(a.concise.claim_ids) <= set(a.detailed.claim_ids):
                raise ValueError("Detailed must keep everything Concise covers")
            if a.detailed.status != "draft" and len(a.detailed.text) <= len(a.concise.text):
                raise ValueError("Detailed must be fuller than Concise")
        s = a.supplement
        if s is not None:
            check_text(s.text, prefix + ".supplement")
            if any(claims[k].required for k in s.text.claim_ids):
                raise ValueError("a supplement cannot hold a required claim")
            if s.text.status == "reviewed" and not s.adds_information:
                raise ValueError("a reviewed supplement must attest it adds information")
            for primary in (a.concise, a.detailed):
                if primary is not None and s.text.text.strip() and s.text.text.strip() in primary.text:
                    raise ValueError("a supplement must not repeat the primary explanation")
    return content


def evaluate31(source: ProcedureSource, content: GuidanceContent31 | None = None, constraints: Constraints | None = None, *, assume_reviewed: bool = False, relax_map: bool = False):
    """Feasibility with D2 and D3 independent. assume_reviewed is a HYPOTHETICAL dry run: drafts count as reviewed, nothing is persisted."""
    constraints = constraints or Constraints()
    g = source.graph
    if content is not None and not assume_reviewed:
        validate_content31(source, content)
    ok = (lambda t: t is not None and (assume_reviewed or t.status == "reviewed"))
    actions = () if content is None else content.actions
    coverage = g.completeness.model_dump()
    structural = all(coverage.get(k) == "complete" for k in ("actions", "conditions", "prerequisites", "branch_groups", "service_dependencies"))
    # relax_map (provisional research preview only): a map of verified branches and prerequisites is truthful when only parallel coverage is unknown, because it claims nothing about parallelism.
    full_map = structural and (relax_map or coverage.get("parallel_groups") == "complete")
    has_relations = bool(g.action_prerequisites or g.branch_groups or g.parallel_groups or g.stage_dependencies or (source.relationships and (source.relationships.joins or source.relationships.parallel_areas)))
    detailed = bool(actions) and all(ok(a.concise) and ok(a.detailed) for a in actions)
    recap = len(g.actions) > 1 and bool(actions) and all(ok(a.recap) for a in actions)
    phases = bool(content and len(content.phases) > 1 and all(ok(p.label) and (p.adds_orientation or assume_reviewed) for p in content.phases))
    eligible = tuple(a.id for a in actions if a.supplement and ok(a.supplement.text) and (a.supplement.adds_information or assume_reviewed) and ok(a.concise))
    out = []
    for config in CATALOGUE:
        reasons = []
        for name, value in config.model_dump().items():
            if name in constraints.locks and value != constraints.locks[name]:
                reasons.append(name + ":hard_lock")
        if config.navigation == "guided" and (len(g.actions) < 2 or not structural or constraints.no_guided):
            reasons.append("navigation:insufficient_structure_or_accessibility")
        if config.explanation == "detailed" and not detailed:
            reasons.append("explanation:reviewed_detailed_missing")
        if config.disclosure == "on":
            if constraints.no_disclosure:
                reasons.append("disclosure:accessibility")
            if not eligible:
                reasons.append("disclosure:no_reviewed_supplement")
        if config.relationships != "none" and not has_relations:
            reasons.append("relationships:no_supplied_relationships")
        if config.relationships == "map" and (not full_map or constraints.no_map):
            reasons.append("relationships:incomplete_map_or_accessibility")
        if config.recap == "on" and not recap:
            reasons.append("recap:reviewed_reminders_missing")
        if config.segmentation == "on" and not phases:
            reasons.append("segmentation:reviewed_meaningful_groups_missing")
        out.append(Candidate(config, tuple(reasons), eligible if config.disclosure == "on" else ()))
    return tuple(out)
