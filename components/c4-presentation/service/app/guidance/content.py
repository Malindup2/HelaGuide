"""Reviewed revised guidance contract. This module has no I/O or model updates.

Coverage checks prove explicit assignment of source spans/IDs, not semantic
entailment of paraphrases. Named statement-level source review remains required.
"""
from typing import Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from app.guidance.sources import ProcedureSource, digest

Status=Literal["draft","reviewed","source_fallback"]

class Record(BaseModel):
    model_config=ConfigDict(extra="forbid",frozen=True,allow_inf_nan=False)

class Text(Record):
    text:str
    status:Status="draft"
    claim_ids:tuple[str,...]=()
    evidence_ids:tuple[str,...]=()

    @model_validator(mode="after")
    def nonempty(self):
        if self.status!="draft" and not self.text.strip():raise ValueError("usable text must not be empty")
        return self

class Claim(Record):
    id:str=Field(min_length=1)
    source_kind:Literal["content","condition"]="content"
    source_id:str
    start:int=Field(ge=0)
    end:int=Field(gt=0)
    quote:str=Field(min_length=1)
    action_ids:tuple[str,...]=Field(min_length=1)
    required:bool=True
    kind:Literal["instruction","condition","document","fee","qualification","destination","actor","clarification"]="instruction"
    evidence_ids:tuple[str,...]=Field(min_length=1)

class ReviewCheck(Record):
    target:str
    claim_ids:tuple[str,...]=()
    evidence_ids:tuple[str,...]=Field(min_length=1)
    result:Literal["matched","rejected"]
    note:str=Field(min_length=1)

class Review(Record):
    status:Literal["draft","reviewed"]="draft"
    reviewer:str=Field(min_length=1)
    reviewed_at:AwareDatetime
    scope_note:str=Field(min_length=1)
    artifact_digest:str
    checks:tuple[ReviewCheck,...]=Field(min_length=1)

class Explanation(Record):
    status:Status="source_fallback"
    remainder:Text | None=None
    remainder_role:Literal["clarification","qualification","background"] | None=None
    adds_information:bool=False

    @model_validator(mode="after")
    def role(self):
        if self.remainder is not None and self.remainder_role is None:raise ValueError("remainder needs a declared role")
        if self.remainder is None and self.remainder_role is not None:raise ValueError("role without remainder")
        return self

class Action(Record):
    id:str
    heading:Text
    heading_actionable:bool=False
    essential:Text
    concise:Explanation=Field(default_factory=Explanation)
    detailed:Explanation | None=None
    recap:Text | None=None
    actor:Text | None=None
    destination:Text | None=None
    visible_condition_ids:tuple[str,...]=()
    visible_attachment_ids:tuple[str,...]=()

class Attachment(Record):
    id:str
    fact_id:str
    scope:Literal["action","route","stage","service"]
    action_id:str | None=None
    stage_id:str | None=None
    service_id:str | None=None
    branch_id:str | None=None
    option_ids:tuple[str,...]=()
    condition_ids:tuple[str,...]=()
    claim_ids:tuple[str,...]=()
    evidence_ids:tuple[str,...]=()
    qualification:Text | None=None
    status:Status="draft"

    @model_validator(mode="after")
    def target(self):
        active={k for k in ("action_id","stage_id","service_id","branch_id") if getattr(self,k) is not None}
        expected={"action":"action_id","stage":"stage_id","service":"service_id","route":"branch_id"}[self.scope]
        if active!={expected} or (self.scope=="route")!=bool(self.option_ids):raise ValueError("attachment needs exactly its scoped target")
        return self

class Phase(Record):
    id:str
    label:Text
    action_ids:tuple[str,...]=Field(min_length=1)
    basis:Literal["purpose","actor","location","timing","stage"]
    why_grouped:str=Field(min_length=1)
    adds_orientation:bool=False
    evidence_ids:tuple[str,...]=Field(min_length=1)
    branch_split_note:str | None=None

class GuidanceContent(Record):
    schema_version:Literal["c4-guidance-content-3.0"]="c4-guidance-content-3.0"
    procedure_id:str
    language:str=Field(default="en",pattern=r"^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
    source_graph_fingerprint:str
    relationship_fingerprint:str
    content_version:str=Field(min_length=1)
    origin:Literal["fictional_authored","human_prepared","provider_generated","source_preserving","demo_mock"]
    source_limit:str
    claims:tuple[Claim,...]
    actions:tuple[Action,...]
    attachments:tuple[Attachment,...]=()
    phases:tuple[Phase,...]=()
    phase_order:tuple[str,...]=()
    phase_order_basis:Literal["none","stage_edges","reviewed_overlay"]="none"
    phase_order_evidence_ids:tuple[str,...]=()
    supplementary:tuple[Text,...]=()
    review:Review | None=None

    @property
    def fingerprint(self):return digest(self.model_dump(mode="json",exclude={"review"}))


def unique(values,label):
    if len(values)!=len(set(values)):raise ValueError("duplicate "+label)


def validate_content(source:ProcedureSource, content:GuidanceContent):
    source.validate();g=source.graph
    if content.procedure_id!=g.plan_id or content.source_graph_fingerprint!=source.graph_fingerprint or content.relationship_fingerprint!=source.relationship_fingerprint:
        raise ValueError("content source/version mismatch")
    if content.source_limit!=g.disclaimer:raise ValueError("source qualification must remain visible verbatim")
    if content.origin=="fictional_authored" and not g.synthetic:raise ValueError("fictional review cannot approve official content")
    actions={a.action_id:a for a in g.actions};facts={f.fact_id:f for f in g.facts};conditions={c.condition_id:c for c in g.conditions};stages={s.service_id:s for s in g.stages};branches={b.group_id:b for b in g.branch_groups};evidence={e.evidence_id for e in g.evidence}
    sources={("content",c.content_id):c.text for c in g.content}|{("condition",c.condition_id):c.text for c in g.conditions}
    unique([c.id for c in content.claims],"claim");unique([a.id for a in content.actions],"action");unique([a.id for a in content.attachments],"attachment");unique([p.id for p in content.phases],"phase")
    if {a.id for a in content.actions}!=set(actions):raise ValueError("content must cover exactly all actions")
    claims={c.id:c for c in content.claims}
    for c in content.claims:
        text=sources.get((c.source_kind,c.source_id))
        if text is None or c.end>len(text) or text[c.start:c.end]!=c.quote:raise ValueError("claim must bind an exact current source span")
        if not set(c.action_ids)<=actions.keys() or not set(c.evidence_ids)<=evidence:raise ValueError("unresolved claim references")
        for aid in c.action_ids:
            a=actions[aid]
            allowed=set(a.required_content_ids)|set(a.supplementary_content_ids) if c.source_kind=="content" else set(a.applicability.condition_ids)
            if c.source_id not in allowed:raise ValueError("claim does not belong to its action")
        source_record=next(r for r in (g.content if c.source_kind=="content" else g.conditions) if (r.content_id if c.source_kind=="content" else r.condition_id)==c.source_id)
        if not set(c.evidence_ids)<=set(source_record.evidence_ids):raise ValueError("claim evidence does not belong to the source passage")
    review=content.review
    reviewed=bool(review and review.status=="reviewed")
    checks={} if not review else {c.target:c for c in review.checks}
    if review:
        unique([c.target for c in review.checks],"review target")
        for c in review.checks:
            if not set(c.claim_ids)<=claims.keys() or not set(c.evidence_ids)<=evidence:raise ValueError("unresolved review references")
    if reviewed:
        if content.origin=="demo_mock":raise ValueError("mock must not be relabelled reviewed")
        if not review.reviewer.strip() or review.reviewer.strip().upper().startswith("PENDING") or review.artifact_digest!=content.fingerprint:
            raise ValueError("review identity/digest mismatch")

    def require_review(target, claim_ids=(), evidence_ids=()):
        check=checks.get(target)
        if not reviewed or check is None or check.result!="matched" or not set(claim_ids)<=set(check.claim_ids) or not set(evidence_ids)<=set(check.evidence_ids):
            raise ValueError("missing named source-fidelity review: "+target)

    def text_field(field,target):
        if field is None:return
        unique(field.claim_ids,"field claim")
        if not set(field.claim_ids)<=claims.keys() or not set(field.evidence_ids)<=evidence:raise ValueError("unresolved text references")
        if field.status=="reviewed":
            if not field.evidence_ids:raise ValueError("reviewed text needs evidence")
            require_review(target,field.claim_ids,field.evidence_ids)
        if field.status=="source_fallback":
            refs=list(dict.fromkeys((claims[k].source_kind,claims[k].source_id) for k in field.claim_ids))
            joined="\n\n".join(sources[ref] for ref in refs)
            if field.text not in sources.values() and (not refs or field.text!=joined):raise ValueError("source fallback must preserve complete source passages")
            if any(claims[k].quote not in field.text for k in field.claim_ids):raise ValueError("fallback claim not present in exact source text")

    attachments={f.id:f for f in content.attachments}
    for f in content.attachments:
        if f.fact_id not in facts or not set(f.condition_ids)<=conditions.keys() or not set(f.claim_ids)<=claims.keys() or not set(f.evidence_ids)<=evidence:raise ValueError("unresolved attachment references")
        if f.scope=="action" and f.action_id not in actions:raise ValueError("unknown fact action")
        if f.scope=="stage" and f.stage_id not in stages:raise ValueError("unknown fact stage")
        if f.scope=="service" and f.service_id!=g.requested_service_id:raise ValueError("service scope must name requested service")
        if f.scope=="route":
            branch=branches.get(f.branch_id)
            if branch is None or not set(f.option_ids)<={o.option_id for o in branch.options}:raise ValueError("unknown fee route")
            required={c for o in branch.options if o.option_id in f.option_ids for c in o.condition_ids}
            if not required<=set(f.condition_ids):raise ValueError("route attachment omitted applicability conditions")
        if f.scope=="stage" and f.fact_id not in {stages[f.stage_id].fee_fact_id,*stages[f.stage_id].document_fact_ids}:raise ValueError("fact does not belong to declared stage")
        if f.scope=="action" and not any(stage.service_id==actions[f.action_id].service_id and f.fact_id in {stage.fee_fact_id,*stage.document_fact_ids} for stage in g.stages):raise ValueError("action fact contradicts source stage ownership")
        if any(claims[k].kind not in ("fee","document") for k in f.claim_ids):raise ValueError("instructions/qualifications cannot hide in fact attachments")
        if f.status=="source_fallback":
            if f.scope!="stage" or f.fact_id not in {stages[f.stage_id].fee_fact_id,*stages[f.stage_id].document_fact_ids}:raise ValueError("fallback cannot infer action/route fee scope")
        if f.status=="reviewed":
            if not f.evidence_ids:raise ValueError("reviewed attribution needs evidence")
            require_review("attachments."+f.id,f.claim_ids,f.evidence_ids)
        text_field(f.qualification,"attachments."+f.id+".qualification")

    for a in content.actions:
        ga=actions[a.id];prefix="actions."+a.id
        if set(a.visible_condition_ids)!=set(ga.applicability.condition_ids):raise ValueError("all essential conditions must stay visible")
        if not set(a.visible_attachment_ids)<=attachments.keys():raise ValueError("unknown visible fact attachment")
        for fid in a.visible_attachment_ids:
            f=attachments[fid]
            if f.scope!="action" or f.action_id!=a.id:raise ValueError("stage/service/route fees cannot become action payments")
        for name in ("heading","essential","recap","actor","destination"):
            text_field(getattr(a,name),prefix+"."+name)
        if a.heading.status=="reviewed" and not a.heading_actionable:raise ValueError("reviewed heading must attest complete actionability")
        if a.recap and a.recap.status=="reviewed" and a.recap.text.strip()==a.heading.text.strip():raise ValueError("recap must remind, not repeat the heading")
        for field in (a.heading,a.essential,a.recap,a.actor,a.destination):
            if field and any(a.id not in claims[k].action_ids for k in field.claim_ids):raise ValueError("text uses another action's claim")
        visible=set(a.essential.claim_ids) if a.essential.status!="draft" else {c.id for c in content.claims if c.required and a.id in c.action_ids}
        for name in ("actor","destination"):
            field=getattr(a,name)
            if field and field.status!="draft":visible.update(field.claim_ids)
        for fid in a.visible_attachment_ids:
            f=attachments[fid]
            if f.status!="draft":
                visible.update(f.claim_ids)
                if f.qualification and f.qualification.status!="draft":visible.update(f.qualification.claim_ids)
        required=[c for c in content.claims if c.required and a.id in c.action_ids]
        if not {c.id for c in required}<=visible:raise ValueError("required claim assigned outside always-visible layer")
        for cid in ga.required_content_ids:
            source_text=sources[("content",cid)]
            spans=[c for c in required if c.source_kind=="content" and c.source_id==cid]
            if any(not any(c.start<=i<c.end for c in spans) for i,ch in enumerate(source_text) if not ch.isspace()):
                raise ValueError("required source passage has uncovered claims")
        for depth in ("concise","detailed"):
            exp=getattr(a,depth)
            if exp is None:continue
            text_field(exp.remainder,prefix+"."+depth+".remainder")
            if exp.remainder and any(claims[k].required for k in exp.remainder.claim_ids):raise ValueError("disclosure remainder contains a required claim")
            if exp.status=="reviewed":
                require_review(prefix+"."+depth)
                if exp.remainder and (exp.remainder.status!="reviewed" or not exp.adds_information):raise ValueError("remainder needs source-reviewed nonduplication")
                if depth=="detailed" and (not exp.remainder or exp.remainder.text==(a.concise.remainder.text if a.concise.remainder else "")):
                    raise ValueError("Detailed must add reviewed meaning to Concise")

    if content.phases:
        if len(content.phases)<2:raise ValueError("segmentation needs at least two meaningful groups")
        membership=[aid for p in content.phases for aid in p.action_ids]
        if len(membership)!=len(set(membership)) or set(membership)!=set(actions):raise ValueError("each action must belong to exactly one phase")
        for p in content.phases:
            text_field(p.label,"phases."+p.id+".label")
            if not set(p.evidence_ids)<=evidence:raise ValueError("unknown phase evidence")
            if p.label.status=="reviewed":
                require_review("phases."+p.id,evidence_ids=p.evidence_ids)
                if not p.adds_orientation:raise ValueError("phase must attest added orientation")
                labels={a.heading.text.strip().casefold() for a in content.actions}|{s.name.strip().casefold() for s in g.stages}
                if p.label.text.strip().casefold() in labels:raise ValueError("phase label merely repeats action/service")
            for b in g.branch_groups:
                group={aid for o in b.options for aid in o.action_ids}
                if group&set(p.action_ids) and not group<=set(p.action_ids) and not p.branch_split_note:
                    raise ValueError("split branch grouping needs a reviewed note")
    if content.phase_order:
        if set(content.phase_order)!={p.id for p in content.phases} or len(content.phase_order)!=len(content.phases) or content.phase_order_basis=="none":raise ValueError("invalid phase order")
        require_review("phase_order",evidence_ids=content.phase_order_evidence_ids)
        if not content.phase_order_evidence_ids or not set(content.phase_order_evidence_ids)<=evidence:raise ValueError("phase order needs source evidence")
        membership={aid:p.id for p in content.phases for aid in p.action_ids};order={p:i for i,p in enumerate(content.phase_order)}
        if any(order[membership[u]]>order[membership[v]] for u,v in source.action_edges()):raise ValueError("phase order contradicts verified dependency")
        if content.phase_order_basis=="stage_edges":
            reach={s.service_id:set() for s in g.stages}
            for e in g.stage_dependencies:reach[e.source_id].add(e.target_id)
            for _ in g.stages:
                for sid in reach:reach[sid].update(*(reach[t].copy() for t in tuple(reach[sid])))
            groups={p.id:{actions[aid].service_id for aid in p.action_ids} for p in content.phases}
            if any(not all(v in reach[u] for u in groups[x] for v in groups[y]) for x,y in zip(content.phase_order,content.phase_order[1:])):
                raise ValueError("phase order lacks verified stage path")
    elif content.phase_order_basis!="none":raise ValueError("order basis without phase order")
    for i,t in enumerate(content.supplementary):
        text_field(t,"supplementary."+str(i))
        if any(claims[k].required for k in t.claim_ids):raise ValueError("required claim cannot be supplementary")
    return content
