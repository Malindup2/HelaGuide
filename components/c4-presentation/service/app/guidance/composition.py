"""Safe render-plan foundation, not an active frontend/API integration."""
from app.guidance.catalogue import Configuration, Constraints
from app.guidance.content import GuidanceContent
from app.guidance.feasibility import evaluate
from app.guidance.sources import ProcedureSource


def compose(source:ProcedureSource, content:GuidanceContent | None, config:Configuration, constraints:Constraints | None=None):
    candidate=next(c for c in evaluate(source,content,constraints) if c.configuration==config)
    if not candidate.feasible:raise ValueError("infeasible guidance configuration: "+", ".join(candidate.reasons))
    g=source.graph;prepared={} if content is None else {a.id:a for a in content.actions}
    passages={c.content_id:c for c in g.content};conditions={c.condition_id:c.text for c in g.conditions}
    facts={f.fact_id:f.model_dump(mode="json") for f in g.facts}
    attachments=[];scoped=set()
    for f in content.attachments if content else ():
        if f.status=="draft":continue
        item=f.model_dump(mode="json",exclude={"qualification"})
        item["fact"]=facts[f.fact_id]
        item["qualification"]=f.qualification.text if f.qualification and f.qualification.status!="draft" else None
        item["conditions"]=[conditions[c] for c in f.condition_ids]
        attachments.append(item);scoped.add(f.fact_id)
    # Default source facts retain their Plan stage scope; mentions never infer payment.
    for stage in g.stages:
        for fid in (stage.fee_fact_id,*stage.document_fact_ids):
            if fid not in scoped:
                attachments.append({"id":"source:"+stage.service_id+":"+fid,"fact":facts[fid],"fact_id":fid,
                    "scope":"stage","stage_id":stage.service_id,"qualification":None,"conditions":[],"status":"source_fallback"})
    result=[]
    for action in g.actions:
        a=prepared.get(action.action_id)
        raw="\n\n".join(passages[c].text for c in action.required_content_ids)
        essential=a.essential.text if a and a.essential.status!="draft" else raw
        heading=a.heading.text if a and a.heading.status!="draft" else raw.split(". ")[0]
        exp=getattr(a,config.explanation) if a else None
        remainder=exp.remainder.text if exp and exp.status=="reviewed" and exp.remainder and exp.remainder.status=="reviewed" else None
        disclosable=action.action_id in candidate.disclosable_action_ids
        result.append({"id":action.action_id,"heading":heading,"essential":essential,
            "conditions":[conditions[c] for c in action.applicability.condition_ids],
            "actor":a.actor.text if a and a.actor and a.actor.status!="draft" else None,
            "destination":a.destination.text if a and a.destination and a.destination.status!="draft" else None,
            "facts":[f for f in attachments if f["scope"]=="action" and f["action_id"]==action.action_id],
            "explanation_visible":None if disclosable else remainder,"explanation_hidden":remainder if disclosable else None,
            "recap":a.recap.text if config.recap=="on" and a and a.recap else None,
            "branch":action.applicability.branch_group_id,"option":action.applicability.branch_option_id})
    return {"schema":"c4-render-plan-3.0","configuration":config.model_dump(),"source_limit":g.disclaimer,
        "source_graph_fingerprint":source.graph_fingerprint,"relationship_fingerprint":source.relationship_fingerprint,
        "content_fingerprint":content.fingerprint if content else None,"actions":result,"facts":attachments,
        "branches":[b.model_dump(mode="json") for b in g.branch_groups],
        "stages":[s.model_dump(mode="json") for s in g.stages],
        "stage_edges":[e.model_dump(mode="json") for e in g.stage_dependencies],
        "edges":[e.model_dump(mode="json") for e in g.action_prerequisites],
        "parallel":[p.model_dump(mode="json") for p in g.parallel_groups],
        "joins":[j.model_dump(mode="json") for j in source.relationships.joins] if source.relationships else [],
        "parallel_areas":[[e.model_dump(mode="json") for e in group] for group in source.relationships.parallel_areas] if source.relationships else [],
        "completeness":g.completeness.model_dump(),
        "sources":[e.model_dump(mode="json") for e in g.evidence],
        "map_labels":{a["id"]:a["heading"] for a in result},
        "phases":[p.model_dump(mode="json") for p in content.phases] if content and config.segmentation=="on" else [],
        "phase_order":list(content.phase_order) if content and config.segmentation=="on" else [],
        "supplementary":[t.text for t in content.supplementary if t.status!="draft"] if content else [],
        "required_source_notes":[passages[c].text for action in g.actions for c in action.supplementary_content_ids]}
