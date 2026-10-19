"""Editable prior judgments; never participant observations or automatic expert evidence."""

from typing import Literal, Self

from pydantic import Field, model_validator

from app.models.procedure_graph import GraphRecord


class PriorSource(GraphRecord):
    source_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=400)
    url: str = Field(pattern=r"^https://", max_length=2000)
    scope: str = Field(min_length=1, max_length=1200)


class PriorJudgment(GraphRecord):
    judgment_id: str = Field(min_length=1, max_length=80)
    context: str = Field(min_length=1, max_length=160)
    aid: Literal["guided", "progressive_disclosure", "previous_context_recap",
                 "branch_map", "dependency_map", "parallel_map", "prerequisite_cue"]
    score_delta: float = Field(ge=-0.05, le=0.05)
    rationale: str = Field(min_length=1, max_length=2000)
    source_ids: tuple[str, ...] = Field(min_length=1)


class PriorSpec(GraphRecord):
    schema_version: Literal["c4-weak-prior-1.0"] = "c4-weak-prior-1.0"
    version: str = Field(min_length=1, max_length=100)
    status: Literal["provisional_pending_expert_validation", "expert_validated"]
    author: str = Field(min_length=1, max_length=200)
    reviewer: str | None = Field(default=None, min_length=1, max_length=200)
    review_reference: str | None = Field(default=None, min_length=1, max_length=1000)
    sources: tuple[PriorSource, ...] = Field(min_length=1, max_length=30)
    judgments: tuple[PriorJudgment, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        sources = {source.source_id for source in self.sources}
        if len(sources) != len(self.sources):
            raise ValueError("duplicate prior source")
        ids = [j.judgment_id for j in self.judgments]
        pairs = [(j.context, j.aid) for j in self.judgments]
        if len(set(ids)) != len(ids) or len(set(pairs)) != len(pairs):
            raise ValueError("duplicate judgment or context/aid coefficient")
        if any(not set(j.source_ids) <= sources for j in self.judgments):
            raise ValueError("judgment cites an unknown source")
        # Each context/aid input is in [0, 1]. Bound total initial score shift.
        if sum(abs(j.score_delta) for j in self.judgments) > 0.25 + 1e-12:
            raise ValueError("total absolute initial score shift must be at most 0.25")
        if self.status == "expert_validated" and not (self.reviewer and self.review_reference):
            raise ValueError("expert validation requires a reviewer and review reference")
        return self
