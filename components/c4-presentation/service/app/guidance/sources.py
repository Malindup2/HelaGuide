"""Read-only source adapter. The existing verified overlay is a temporary bridge.

No wording, relationships or measurements are generated here. The active V2
modules are unchanged; their structural types can be extracted after cutover.
"""
import hashlib
import json
from pydantic import BaseModel, ConfigDict
from app.models.procedure_graph import CanonicalProcedureGraph
from app.procedures.scaffolds import graph_fingerprint
from app.procedures.canonical import Overlay, validate_overlay


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",", ":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


class ProcedureSource(BaseModel):
    model_config=ConfigDict(extra="forbid", frozen=True)
    graph: CanonicalProcedureGraph
    relationships: Overlay | None = None

    @property
    def graph_fingerprint(self):
        return graph_fingerprint(self.graph)

    @property
    def relationship_fingerprint(self):
        extension=self.relationships.model_dump(mode="json",exclude={"reviewer","variants","optional_content_ids"}) if self.relationships else None
        return digest({"graph":self.graph_fingerprint,"extension":extension})

    def validate(self):
        if self.relationships:
            validate_overlay(self.graph,self.relationships)
        return self

    def action_edges(self):
        edges=[(e.source_id,e.target_id) for e in self.graph.action_prerequisites]
        branches={b.group_id:b for b in self.graph.branch_groups}
        def leaves(e):
            if e.kind=="action":return {e.ref}
            if e.kind=="selected_option_of":return {a for o in branches[e.ref].options for a in o.action_ids}
            return set().union(*(leaves(c) for c in e.children))
        for join in self.relationships.joins if self.relationships else ():
            edges.extend((a,join.target) for a in leaves(join.requirement))
        return edges
