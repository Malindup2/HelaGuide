"""Revised actions only; no encoder, learned policy or selection rules."""
from itertools import product
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

ACTION_SCHEMA="c4-scaffolds-v3.0"
DIMENSIONS={"navigation":("overview","guided"),"explanation":("concise","detailed"),
    "disclosure":("off","on"),"relationships":("none","inline","map"),
    "recap":("off","on"),"segmentation":("off","on")}

class Configuration(BaseModel):
    model_config=ConfigDict(extra="forbid",frozen=True)
    navigation:Literal["overview","guided"]="overview"
    explanation:Literal["concise","detailed"]="concise"
    disclosure:Literal["off","on"]="off"
    relationships:Literal["none","inline","map"]="none"
    recap:Literal["off","on"]="off"
    segmentation:Literal["off","on"]="off"

    @property
    def key(self):return ACTION_SCHEMA+":"+":".join(self.model_dump().values())

class Constraints(BaseModel):
    model_config=ConfigDict(extra="forbid",frozen=True)
    locks:dict[str,str]=Field(default_factory=dict)
    no_guided:bool=False
    no_map:bool=False
    no_disclosure:bool=False

    @model_validator(mode="after")
    def validate_locks(self):
        if any(k not in DIMENSIONS or v not in DIMENSIONS[k] for k,v in self.locks.items()):
            raise ValueError("unknown revised scaffold lock")
        return self

CATALOGUE=tuple(Configuration(**dict(zip(DIMENSIONS,values))) for values in product(*DIMENSIONS.values()))
assert len(CATALOGUE)==96
