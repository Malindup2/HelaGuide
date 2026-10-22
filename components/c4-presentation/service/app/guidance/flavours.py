"""Content/action-semantics flavours. The default is the historical 3.0 behaviour, unchanged.

A flavour bundles everything that depends on what the six scaffolds MEAN, so a runtime can never mix 3.0 and 3.1 meanings:
schemas, feasibility, composition, registry, demo content and which policy manifest (if any) is compatible.
"""
from dataclasses import dataclass
from typing import Any, Callable
from app.guidance import v31_pipeline as p31
from app.guidance.catalogue import ACTION_SCHEMA
from app.guidance.composition import compose
from app.guidance.content import GuidanceContent
from app.guidance.content_v31 import SCHEMA31, GuidanceContent31, evaluate31
from app.guidance.demo import install_fictional_content
from app.guidance.feasibility import evaluate
from app.guidance.policy import PROFILE_30
from app.guidance.registry import CONTENT_SCHEMA, ContentRegistry, cache_key


@dataclass(frozen=True)
class Flavour:
    name: str
    content_schema: str
    action_schema: str
    render_schema: str
    content_model: Any
    evaluate: Callable
    compose: Callable
    make_registry: Callable
    cache_key: Callable
    install_demo: Callable
    config_key: Callable
    feasibility_fingerprint: Callable | None
    supports_policy: bool
    policy_profile: Any = None
    policy_manifest: Callable | None = None


FLAVOUR_30 = Flavour("3.0", CONTENT_SCHEMA, ACTION_SCHEMA, "c4-render-plan-3.0", GuidanceContent, evaluate, compose, ContentRegistry, cache_key,
                     install_fictional_content, lambda c: c.key, None, True, PROFILE_30)
FLAVOUR_31 = Flavour("3.1", SCHEMA31, p31.ACTION_SCHEMA31, p31.RENDER_SCHEMA31, GuidanceContent31, evaluate31, p31.compose31, p31.ContentRegistry31,
                     p31.cache_key31, p31.install_fictional_content31, p31.config_key31, p31.feasibility_fingerprint, True, p31.PROFILE_31, p31.manifest31)


def by_content_schema(value: str | None) -> Flavour:
    if value in (None, "", FLAVOUR_30.content_schema):
        return FLAVOUR_30
    if value == FLAVOUR_31.content_schema:
        return FLAVOUR_31
    raise ValueError("unknown content schema: " + str(value))
