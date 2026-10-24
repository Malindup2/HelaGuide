"""Future scoring-stage interfaces only. No encoder or history estimator exists here."""
from typing import Literal, Protocol
from pydantic import AwareDatetime, Field, model_validator
from app.guidance.content import Record
from app.guidance.catalogue import ACTION_SCHEMA

class BaseScore(Record):
    candidate_id:str
    sampled_score:float

class HistoryGate(Record):
    """Evidence assessment record; names/rules and thresholds need later approval."""
    name:str=Field(min_length=1)
    outcome:Literal["passed","failed","not_assessed"]
    evidence_ids:tuple[str,...]=()
    reason:str=Field(min_length=1)

class HistoryAdjustment(Record):
    history_schema:str
    cutoff_timestamp:AwareDatetime
    gates:tuple[HistoryGate,...]=()
    abstained:bool
    reasons:tuple[str,...]
    evidence_ids:tuple[str,...]=()
    bound:float | None=Field(default=None,ge=0)
    adjustments:dict[str,float]=Field(default_factory=dict)

    @model_validator(mode="after")
    def bounded(self):
        names=[g.name for g in self.gates]
        if len(names)!=len(set(names)):raise ValueError("duplicate history gate record")
        if not self.abstained and (not {"relevance","consistency","uncertainty"}<=set(names) or any(g.outcome!="passed" for g in self.gates)):
            raise ValueError("active adjustment needs recorded passed relevance, consistency and uncertainty gates")
        if self.abstained and (any(self.adjustments.values()) or not self.reasons):raise ValueError("abstention must be exact with a reason")
        if not self.abstained and (self.bound is None or not self.evidence_ids):raise ValueError("active history stage requires explicit bound and evidence")
        if self.bound is not None and any(abs(v)>self.bound for v in self.adjustments.values()):raise ValueError("history contribution exceeds declared bound")
        return self

class SelectionRecord(Record):
    schema_version:Literal["c4-selection-record-3.0"]="c4-selection-record-3.0"
    action_schema:Literal["c4-scaffolds-v3.0"]=ACTION_SCHEMA
    encoder_schema:str  # Still awaiting approval; no feature ordering defined.
    feasible_candidate_ids:tuple[str,...]
    base_scores:tuple[BaseScore,...]
    base_winner:str
    history:HistoryAdjustment
    selected_candidate:str

    @model_validator(mode="after")
    def trace_integrity(self):
        ids=[s.candidate_id for s in self.base_scores]
        if not ids or len(ids)!=len(set(ids)) or len(self.feasible_candidate_ids)!=len(set(self.feasible_candidate_ids)) or set(ids)!=set(self.feasible_candidate_ids):raise ValueError("scores must cover exactly the feasible set")
        if not set(self.history.adjustments)<=set(ids):raise ValueError("history cannot introduce infeasible candidates")
        base=max(self.base_scores,key=lambda s:s.sampled_score).candidate_id
        final=max(self.base_scores,key=lambda s:s.sampled_score+self.history.adjustments.get(s.candidate_id,0)).candidate_id
        if self.base_winner!=base or self.selected_candidate!=final:raise ValueError("selection record does not match frozen scores")
        if self.history.adjustments.get(base,0)!=0:raise ValueError("history must be anchored at the base winner")
        return self

class BaseScorer(Protocol):
    def score(self, context, procedure, feasible_candidates) -> tuple[BaseScore,...]: ...

class HistoryStage(Protocol):
    def assess(self, context, procedure, base_scores, history_snapshot) -> HistoryAdjustment: ...
