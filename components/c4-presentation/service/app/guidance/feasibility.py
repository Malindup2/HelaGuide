"""Candidate-level feasibility for revised semantics; never predicts benefit."""
from dataclasses import dataclass
from app.guidance.catalogue import CATALOGUE, Configuration, Constraints
from app.guidance.content import GuidanceContent, validate_content
from app.guidance.sources import ProcedureSource

@dataclass(frozen=True)
class Candidate:
    configuration:Configuration
    reasons:tuple[str,...]
    disclosable_action_ids:tuple[str,...]=()

    @property
    def feasible(self):return not self.reasons


def evaluate(source:ProcedureSource, content:GuidanceContent | None=None, constraints:Constraints | None=None):
    source.validate();g=source.graph;constraints=constraints or Constraints()
    if content:validate_content(source,content)
    actions=() if content is None else content.actions
    coverage=g.completeness.model_dump()
    structural=all(coverage.get(k)=="complete" for k in ("actions","conditions","prerequisites","branch_groups","service_dependencies"))
    full_map=structural and coverage.get("parallel_groups")=="complete"
    has_relations=bool(g.action_prerequisites or g.branch_groups or g.parallel_groups or g.stage_dependencies or (source.relationships and (source.relationships.joins or source.relationships.parallel_areas)))
    detailed=bool(actions) and all(a.detailed and a.detailed.status=="reviewed" for a in actions)
    recap=len(g.actions)>1 and bool(actions) and all(a.recap and a.recap.status=="reviewed" for a in actions)
    phases=bool(content and len(content.phases)>1 and all(p.label.status=="reviewed" and p.adds_orientation for p in content.phases))
    results=[]
    for config in CATALOGUE:
        reasons=[]
        for name,value in config.model_dump().items():
            if name in constraints.locks and value!=constraints.locks[name]:reasons.append(name+":hard_lock")
        if config.navigation=="guided" and (len(g.actions)<2 or not structural or constraints.no_guided):reasons.append("navigation:insufficient_structure_or_accessibility")
        if config.explanation=="detailed" and not detailed:reasons.append("explanation:reviewed_detailed_missing")
        eligible=[]
        for action in actions:
            exp=getattr(action,config.explanation)
            if exp and exp.status=="reviewed" and exp.remainder and exp.remainder.status=="reviewed" and exp.adds_information and action.essential.status!="draft":eligible.append(action.id)
        if config.disclosure=="on":
            if constraints.no_disclosure:reasons.append("disclosure:accessibility")
            if not eligible:reasons.append("disclosure:no_reviewed_remainder_for_selected_depth")
        if config.relationships!="none" and not has_relations:reasons.append("relationships:no_supplied_relationships")
        if config.relationships=="map" and (not full_map or constraints.no_map):reasons.append("relationships:incomplete_map_or_accessibility")
        if config.recap=="on" and not recap:reasons.append("recap:reviewed_reminders_missing")
        if config.segmentation=="on" and not phases:reasons.append("segmentation:reviewed_meaningful_groups_missing")
        results.append(Candidate(config,tuple(reasons),tuple(eligible) if config.disclosure=="on" else ()))
    return tuple(results)
