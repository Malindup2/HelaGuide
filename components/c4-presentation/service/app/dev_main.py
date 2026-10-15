"""Independent, localhost-only C4 research development API.

Run:
    python -m uvicorn app.dev_main:app --host 127.0.0.1 --port 8016

This is separate from app.main and the team's shared stub.
No feedback updates or automatic exposure acknowledgments occur here.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from threading import RLock

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from app.core.explanations import ExplanationService
from app.core.llm_provider import OpenAIExplanationProvider
from app.core.policy import NoFeasibleConfigurationError, SharedLinTSPolicy
from app.core.presentation import (
    action_navigation_order,
    build_presentation_spec,
)
from app.core.procedure_features import extract_structural_features
from app.core.procedure_graph import build_procedure_graph
from app.core.procedure_input import load_procedure_input
from app.core.scaffolds import graph_fingerprint
from app.core.user_context import (
    ContextConflictError,
    ContextError,
    InMemoryContextService,
    UnknownSessionError,
)
from app.models.policy import PolicyOffer
from app.models.presentation import PresentationSpec
from app.models.procedure import ActionId
from app.models.procedure_graph import CanonicalProcedureGraph
from app.models.scaffolds import ContentSafety
from app.models.user_context import (
    ContextEvaluation,
    ContextUpdate,
    GuestSession,
    PresentationExposure,
)


class RequestModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class ContextRequest(RequestModel):
    expected_revision: int = Field(ge=0)
    update: ContextUpdate


class PresentationRequest(RequestModel):
    procedure_id: str
    expected_revision: int = Field(ge=0)
    focus_action_id: ActionId | None = None


class AcknowledgmentRequest(RequestModel):
    presentation_id: str
    configuration_id: str
    displayed_action_ids: list[ActionId] = Field(min_length=1)


class PresentationResponse(BaseModel):
    spec: PresentationSpec
    stale_for_display: bool


class DevRuntime:
    """One process-local integration of existing C4 services."""

    def __init__(self, provider, graphs, safety_by_fingerprint):
        self.lock = RLock()
        self.contexts = InMemoryContextService()
        self.policy = SharedLinTSPolicy(self.contexts)
        self.explanations = ExplanationService(provider)
        self.provider = provider

        self.procedures = {}
        for graph in graphs:
            fingerprint = graph_fingerprint(graph)
            if fingerprint in self.procedures:
                raise ValueError("duplicate registered procedure fingerprint")
            safety = safety_by_fingerprint.get(fingerprint, ContentSafety())
            self.procedures[fingerprint] = (
                graph,
                extract_structural_features(graph),
                safety,
            )

        unknown_reviews = set(safety_by_fingerprint) - set(self.procedures)
        if unknown_reviews:
            raise ValueError("safety review supplied for an unregistered graph")

        self.presentations: dict[str, PresentationSpec] = {}

    def procedure(self, procedure_id):
        try:
            return self.procedures[procedure_id]
        except KeyError:
            raise HTTPException(404, "unknown procedure") from None

    def session(self, session_id):
        try:
            return self.contexts.get_session(session_id)
        except UnknownSessionError:
            raise HTTPException(404, "unknown session") from None

    def presentation(self, session_id, exposure_id):
        self.session(session_id)
        spec = self.presentations.get(exposure_id)
        if spec is None or spec.session_id != session_id:
            raise HTTPException(404, "unknown presentation")
        return spec

    def response(self, spec):
        session = self.session(spec.session_id)
        selected = self.policy.get_offer(spec.exposure_id)
        return PresentationResponse(
            spec=spec,
            stale_for_display=(
                session.settings != selected.offer.context_snapshot.settings
            ),
        )


def _default_graphs():
    fixture = (
        Path(__file__).resolve().parents[2]
        / "research"
        / "data"
        / "fixtures"
        / "linear"
    )
    return (
        build_procedure_graph(
            load_procedure_input(
                fixture / "plan.json",
                fixture / "enrichment.json",
            )
        ),
    )


def create_app(
    *,
    provider=None,
    graphs: tuple[CanonicalProcedureGraph, ...] | None = None,
    safety_by_fingerprint: dict[str, ContentSafety] | None = None,
) -> FastAPI:
    """Create an independent app.

    Inject a fake provider in tests. The default provider is disabled.
    Live use requires an explicit process-level C4_DEV_LLM_ENABLED=true.
    """

    @asynccontextmanager
    async def lifespan(application):
        active_provider = provider
        owns_provider = active_provider is None
        if active_provider is None:
            enabled = os.getenv("C4_DEV_LLM_ENABLED", "false").lower()
            if enabled not in {"true", "false"}:
                raise ValueError("C4_DEV_LLM_ENABLED must be true or false")
            active_provider = (
                OpenAIExplanationProvider.from_environment()
                if enabled == "true"
                else OpenAIExplanationProvider(enabled=False)
            )

        runtime = DevRuntime(
            active_provider,
            _default_graphs() if graphs is None else graphs,
            safety_by_fingerprint or {},
        )
        application.state.runtime = runtime
        try:
            yield
        finally:
            if owns_provider:
                active_provider.close()

    application = FastAPI(
        title="HelaGuide C4 Independent Research API",
        version="0.5.0",
        lifespan=lifespan,
        description=(
            "Local research prototype. Sources may be synthetic. "
            "Presentation creation is not exposure acknowledgment. "
            "Session identifiers are not production authentication."
        ),
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type"],
    )

    def runtime() -> DevRuntime:
        return application.state.runtime

    @application.get("/health")
    def health():
        return {
            "service": "c4-independent-dev",
            "status": "ok",
            "storage": "in_memory",
            "exposure_requires_acknowledgment": True,
        }

    @application.get("/dev/v1/procedures")
    def procedures():
        with runtime().lock:
            return [
                {
                    "procedure_id": fingerprint,
                    "plan_id": graph.plan_id,
                    "requested_service_id": graph.requested_service_id,
                    "synthetic": graph.synthetic,
                    "disclaimer": graph.disclaimer,
                    "action_ids": action_navigation_order(graph),
                    "completeness": graph.completeness,
                    "features": features,
                }
                for fingerprint, (graph, features, safety)
                in runtime().procedures.items()
            ]

    @application.post(
        "/dev/v1/sessions",
        response_model=GuestSession,
        status_code=201,
    )
    def create_session():
        with runtime().lock:
            return runtime().contexts.create_session()

    @application.get(
        "/dev/v1/sessions/{session_id}",
        response_model=GuestSession,
    )
    def get_session(session_id: str):
        with runtime().lock:
            return runtime().session(session_id)

    @application.patch(
        "/dev/v1/sessions/{session_id}/context",
        response_model=GuestSession,
    )
    def update_context(session_id: str, request: ContextRequest):
        with runtime().lock:
            runtime().session(session_id)
            try:
                return runtime().contexts.update_context(
                    session_id,
                    request.update,
                    expected_revision=request.expected_revision,
                )
            except ContextConflictError as exc:
                raise HTTPException(409, str(exc)) from None

    @application.get(
        "/dev/v1/sessions/{session_id}/feasibility/{procedure_id}",
        response_model=ContextEvaluation,
    )
    def feasibility(session_id: str, procedure_id: str):
        with runtime().lock:
            runtime().session(session_id)
            graph, features, safety = runtime().procedure(procedure_id)
            return runtime().contexts.evaluate(
                session_id, graph, features, safety=safety
            )

    @application.post(
        "/dev/v1/sessions/{session_id}/presentations",
        response_model=PresentationResponse,
        status_code=201,
    )
    def create_presentation(session_id: str, request: PresentationRequest):
        with runtime().lock:
            session = runtime().session(session_id)
            if request.expected_revision != session.revision:
                raise HTTPException(409, "session revision changed")
            graph, features, safety = runtime().procedure(request.procedure_id)
            order = action_navigation_order(graph)
            if not order:
                raise HTTPException(
                    422,
                    "this policy integration requires detailed actions",
                )
            if (
                request.focus_action_id is not None
                and request.focus_action_id not in order
            ):
                raise HTTPException(422, "unknown focus action")

            try:
                selected = runtime().policy.select_and_offer(
                    session_id,
                    graph,
                    features,
                    intended_action_ids=order,
                    safety=safety,
                )
            except NoFeasibleConfigurationError:
                evaluation = runtime().contexts.evaluate(
                    session_id, graph, features, safety=safety
                )
                raise HTTPException(
                    409,
                    detail={
                        "code": "no_feasible_configuration",
                        "message": "Review explicit locks and accessibility constraints.",
                        "evaluation": evaluation.model_dump(mode="json"),
                    },
                ) from None
            except ContextConflictError as exc:
                raise HTTPException(409, str(exc)) from None

            result = runtime().explanations.explain(
                graph, selected, safety=safety
            )
            spec = build_presentation_spec(
                graph,
                selected,
                result,
                focus_action_id=request.focus_action_id,
                safety=safety,
            )
            runtime().presentations[spec.exposure_id] = spec
            return runtime().response(spec)

    @application.get(
        "/dev/v1/sessions/{session_id}/presentations/{exposure_id}",
        response_model=PresentationResponse,
    )
    def get_presentation(session_id: str, exposure_id: str):
        with runtime().lock:
            spec = runtime().presentation(session_id, exposure_id)
            return runtime().response(spec)

    @application.get(
        "/dev/v1/sessions/{session_id}/presentations/{exposure_id}/inspector",
        response_model=PolicyOffer,
    )
    def inspector(session_id: str, exposure_id: str):
        with runtime().lock:
            runtime().presentation(session_id, exposure_id)
            return runtime().policy.get_offer(exposure_id)

    @application.post(
        "/dev/v1/sessions/{session_id}/presentations/{exposure_id}/ack",
        response_model=PresentationExposure,
    )
    def acknowledge(
        session_id: str,
        exposure_id: str,
        request: AcknowledgmentRequest,
    ):
        with runtime().lock:
            spec = runtime().presentation(session_id, exposure_id)
            if (
                request.presentation_id != spec.presentation_id
                or request.configuration_id != spec.configuration.configuration_id
            ):
                raise HTTPException(409, "presentation identity mismatch")

            displayed = tuple(request.displayed_action_ids)
            if (
                len(displayed) != len(set(displayed))
                or not set(displayed) <= set(spec.acknowledgment_action_ids)
            ):
                raise HTTPException(
                    422,
                    "displayed actions are outside this presentation's acknowledgment scope",
                )

            try:
                return runtime().contexts.acknowledge_exposure(
                    session_id,
                    exposure_id,
                    configuration_id=request.configuration_id,
                    displayed_action_ids=displayed,
                )
            except ContextConflictError as exc:
                raise HTTPException(409, str(exc)) from None
            except ContextError as exc:
                raise HTTPException(422, str(exc)) from None

    return application


app = create_app()