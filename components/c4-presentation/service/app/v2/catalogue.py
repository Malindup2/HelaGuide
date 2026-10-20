"""V2 action semantics. N/A is capability metadata, never another arm."""
from itertools import product
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal

DIMENSIONS = {
    "navigation": ("overview", "guided"),
    "explanation": ("concise", "expanded"),
    "disclosure": ("collapsed", "expanded"),
    "relationships": ("none", "inline", "map"),
    "recap": ("off", "on"),
    "summary": ("off", "on"),
}
ACTION_SCHEMA = "c4-scaffolds-v2.1"

class Configuration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    navigation: Literal["overview", "guided"] = "overview"
    explanation: Literal["concise", "expanded"] = "concise"
    disclosure: Literal["collapsed", "expanded"] = "collapsed"
    relationships: Literal["none", "inline", "map"] = "none"
    recap: Literal["off", "on"] = "off"
    summary: Literal["off", "on"] = "off"

    @property
    def key(self):
        return "v2:" + ":".join(self.model_dump().values())

class Context(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    familiarity: int | None = Field(default=None, ge=1, le=5)
    confidence: int | None = Field(default=None, ge=1, le=5)
    preferences: dict[str, str] = Field(default_factory=dict)
    locks: dict[str, str] = Field(default_factory=dict)
    # Explicit accessibility constraints, not inferred diagnoses.
    no_map: bool = False
    no_guided: bool = False
    no_collapsed: bool = False

    @model_validator(mode="after")
    def choices(self):
        for mapping in (self.preferences, self.locks):
            if any(k not in DIMENSIONS or v not in DIMENSIONS[k] for k, v in mapping.items()):
                raise ValueError("unknown scaffold preference or lock")
        return self

CATALOGUE = tuple(Configuration(**dict(zip(DIMENSIONS, values)))
                  for values in product(*DIMENSIONS.values()))
assert len(CATALOGUE) == 96

def evaluate(capabilities: dict, context: Context):
    result = []
    for config in CATALOGUE:
        reasons = []
        for dimension, value in config.model_dump().items():
            allowed = capabilities[dimension]["states"]
            if value not in allowed:
                reasons.append(f"{dimension}: {capabilities[dimension]['reason']}")
            if dimension in context.locks and context.locks[dimension] != value:
                reasons.append(f"{dimension}: explicit hard lock")
        if context.no_map and config.relationships == "map":
            reasons.append("map disabled by accessibility constraint")
        if context.no_guided and config.navigation == "guided":
            reasons.append("guided disabled by accessibility constraint")
        if context.no_collapsed and config.disclosure == "collapsed" and capabilities["disclosure"]["applicable"]:
            reasons.append("collapsed optional content disabled by accessibility constraint")
        result.append({"configuration": config.model_dump(), "id": config.key, "reasons": reasons})
    return result
