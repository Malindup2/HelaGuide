"""Independent, localhost-only C4 research development API.

Run:
    python -m uvicorn app.dev_main:app --host 127.0.0.1 --port 8016

This is separate from app.main and the team's shared stub.
No feedback updates or automatic exposure acknowledgments occur here.
"""

import os
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from typing import Literal
from pathlib import Path
from threading import RLock

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from fastapi.responses import JSONResponse

from app.core.policy import (
    FEATURE_DIMENSION,
    FEATURE_SCHEMA_FINGERPRINT,
    FEATURE_SCHEMA_VERSION,
    FeedbackConflictError,
    PolicyError,
)
from app.core.state_store import SQLiteStateStore, StateStoreError
from app.models.policy import PolicyConfig, SupportFitFeedback
from app.models.runtime_state import AcceptedFeedback, RuntimeState

from app.core.explanations import ExplanationService
from app.core.explanation_store import ExplanationArtifactStore
from app.core.wording_views import WordingViews
from app.models.prepared_wording import WordingResolution
from app.core.llm_provider import OpenAIExplanationProvider
from app.core.policy import NoFeasibleConfigurationError, SharedLinTSPolicy
from app.core.presentation import (
    action_navigation_order,
    build_presentation_spec,
)
from app.core.procedure_features import extract_structural_features
from app.core.demo_procedures import load_demo_procedures
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
    ContextEvent,
    ContextUpdate,
    GuestSession,
    PresentationExposure,
    ActionDisplay,
    EventId,
)



from app.core.corrections import (
    apply_correction,
    correction_options,
    record_correction,
    restore_corrections,
)
from app.models.corrections import (
    ApplyCorrectionRequest,
    CorrectionOptions,
    CorrectionRecord,
    CorrectionRequest,
)


from app.api.demo_profiles import register_demo_profile_routes
from app.api.guidance import register_guidance_routes
from app.core.guidance_access import (
    episode_is_active,
    require_active_episode,
    require_personalization,
)
from app.core.demo_profiles import restore_profiles
from app.models.demo_profiles import DemoProfile


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


class FeedbackRequest(RequestModel):
    presentation_id: str
    configuration_id: str
    decision_id: str
    rating: Literal["about_right", "need_more", "too_much"]


class PresentationResponse(BaseModel):
    spec: PresentationSpec
    stale_for_display: bool
    wording: WordingResolution | None = None



class SessionHistoryResponse(BaseModel):
    """Current session and its existing ordered context events.

    Reading this response does not acknowledge display or update learning.
    Feedback remains available through the existing feedback endpoint.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["c4-session-history-1.0"] = (
        "c4-session-history-1.0"
    )
    session: GuestSession
    events: tuple[ContextEvent, ...]

class ActionDisplayRequest(RequestModel):
    event_id: EventId
    expected_revision: int = Field(ge=0)
    presentation_id: str = Field(min_length=1)
    configuration_id: str = Field(min_length=1)
    action_id: ActionId


class NavigationResponse(BaseModel):
    schema_version: Literal["c4-navigation-1.0"] = "c4-navigation-1.0"
    presentation_id: str
    exposure_id: str
    configuration_id: str
    graph_fingerprint: str
    session_revision: int
    acknowledged: bool
    current_action_id: ActionId | None
    displayed_action_ids: tuple[ActionId, ...]
    events: tuple[ActionDisplay, ...]

    

class DevRuntime:
    """Existing C4 services with optional atomic local persistence."""

    def __init__(
        self,
        provider,
        graphs,
        safety_by_fingerprint,
        *,
        database_path=None,
        policy_config=None,
        postgres_dsn=None,
        allow_legacy_adaptive_sessions=True,
        content_directory=None,
        reviewed_content_only=False,
        generation_enabled=True,
        prepared_wording_directory=None,
        wording_views_directory=None,
    ):
        self.lock = RLock()
        self.allow_legacy_adaptive_sessions = allow_legacy_adaptive_sessions
        self.policy_config = policy_config or PolicyConfig()
        self.contexts = InMemoryContextService()
        self.policy = SharedLinTSPolicy(
            self.contexts, config=self.policy_config
        )
        self.explanations = ExplanationService(
            provider,
            artifact_store=(
                ExplanationArtifactStore(content_directory)
                if content_directory is not None else None
            ),
            reviewed_only=reviewed_content_only,
            generation_enabled=generation_enabled,
        )
        self.provider = provider
        self.wording_views = WordingViews(prepared_wording_directory, wording_views_directory)
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

        if set(safety_by_fingerprint) - set(self.procedures):
            raise ValueError("safety review supplied for an unregistered graph")

        self.presentations: dict[str, PresentationSpec] = {}
        self.feedback: dict[str, AcceptedFeedback] = {}
        self.corrections: dict[str, CorrectionRecord] = {}
        self.profiles: dict[str, DemoProfile] = {}
        self.store = None
        self.storage_backend = "in_memory"
        self._store_revision = 0
        self._failed = False

        if database_path is not None and postgres_dsn is not None:
            raise ValueError("choose either SQLite or PostgreSQL storage")

        if postgres_dsn is not None:
            from app.core.postgres_state_store import PostgreSQLStateStore

            self.store = PostgreSQLStateStore(
                postgres_dsn, self.policy_config
            )
            self.storage_backend = "postgresql"
        elif database_path is not None:
            self.store = SQLiteStateStore(database_path, self.policy_config)
            self.storage_backend = "sqlite"

        if self.store is not None:
            try:
                revision, state = self.store.load()
                if state is None:
                    self._store_revision = self.store.save(
                        self.export_state(), expected_revision=0
                    )
                else:
                    self._restore(state)
                    self._store_revision = revision
            except Exception:
                self.store.close()
                raise

    def export_state(self) -> RuntimeState:
        return RuntimeState(
            sessions=self.contexts.export_state(),
            policy=self.policy.export_state(),
            presentations=tuple(
                self.presentations[key]
                for key in sorted(self.presentations)
            ),
            feedback=tuple(
                sorted(
                    self.feedback.values(),
                    key=lambda value: (
                        value.receipt.resulting_posterior_revision
                    ),
                )
            ),
            corrections=tuple(
                self.corrections[key]
                for key in sorted(self.corrections)
            ),
            profiles=tuple(
                self.profiles[key]
                for key in sorted(self.profiles)
            ),
        )

    def _restore(self, state: RuntimeState):
        if state.policy.config != self.policy_config:
            raise StateStoreError("saved policy configuration differs")

        contexts = InMemoryContextService.from_state(state.sessions)
        policy = SharedLinTSPolicy.from_state(contexts, state.policy)
        presentations = {}

        for spec in state.presentations:
            if spec.exposure_id in presentations:
                raise StateStoreError("duplicate saved presentation")
            selected = policy.get_offer(spec.exposure_id)
            offer = selected.offer
            graph = spec.explanation.source.graph

            if (
                spec.session_id != offer.session_id
                or spec.decision_id != selected.decision.decision_id
                or spec.context_revision != offer.context_snapshot.revision
                or spec.configuration != offer.configuration
                or spec.graph_fingerprint != offer.graph_fingerprint
                or graph_fingerprint(graph) != offer.graph_fingerprint
                or extract_structural_features(graph)
                != selected.decision.structural_features
                or not set(spec.acknowledgment_action_ids)
                <= set(offer.intended_action_ids)
            ):
                raise StateStoreError("saved presentation attribution differs")
            presentations[spec.exposure_id] = spec

        policy_offer_ids = {
            selected.offer.exposure_id for selected in state.policy.offers
        }
        context_offer_ids = {
            offer.exposure_id
            for session in state.sessions
            for offer in session.offers
        }
        if (
            set(presentations) != policy_offer_ids
            or context_offer_ids != policy_offer_ids
        ):
            raise StateStoreError("saved offers and presentations differ")

        acknowledgments = {}
        for session in state.sessions:
            for event in session.events:
                if isinstance(event, PresentationExposure):
                    spec = presentations[event.offer.exposure_id]
                    if not set(event.displayed_action_ids) <= set(
                        spec.acknowledgment_action_ids
                    ):
                        raise StateStoreError("saved display scope differs")
                    acknowledgments[event.offer.exposure_id] = event

                elif isinstance(event, ActionDisplay):
                    spec = presentations.get(event.exposure_id)
                    if (
                        spec is None
                        or spec.session_id != event.session_id
                        or spec.presentation_id != event.presentation_id
                        or spec.configuration.configuration_id
                        != event.configuration_id
                        or event.action_id
                        not in {page.action_id for page in spec.pages}
                    ):
                        raise StateStoreError(
                            "saved navigation attribution differs"
                        )

        receipts = {
            receipt.feedback.exposure_id: receipt
            for receipt in state.policy.receipts
        }
        feedback = {}
        for accepted in state.feedback:
            exposure_id = accepted.receipt.feedback.exposure_id
            acknowledgment = acknowledgments.get(exposure_id)
            if (
                exposure_id in feedback
                or receipts.get(exposure_id) != accepted.receipt
                or acknowledgment is None
                or accepted.accepted_at < acknowledgment.acknowledged_at
            ):
                raise StateStoreError("saved feedback record differs")
            feedback[exposure_id] = accepted

        if set(feedback) != set(receipts):
            raise StateStoreError("saved feedback and policy receipts differ")

        corrections = restore_corrections(
            state.corrections,
            presentations,
            feedback,
            contexts,
        )

        profiles = restore_profiles(
            state.profiles,
            contexts,
        )

        # Publish recovered state only after all checks succeed.
        self.contexts = contexts
        self.policy = policy
        self.presentations = presentations
        self.feedback = feedback
        self.corrections = corrections
        self.profiles = profiles

    def assert_available(self):
        with self.lock:
            if self._failed:
                raise StateStoreError(
                    "runtime requires restart after a persistence failure"
                )
            if self.store is not None:
                try:
                    self.store.assert_revision(self._store_revision)
                except StateStoreError:
                    self._failed = True
                    raise

    @contextmanager
    def change(self):
        """Commit a complete operation or restore its prior in-memory state."""
        with self.lock:
            self.assert_available()
            before = self.export_state()
            try:
                yield
                after = self.export_state()
            except Exception:
                try:
                    self._restore(before)
                except Exception:
                    self._failed = True
                    raise StateStoreError("runtime rollback failed; restart") from None
                raise

            if self.store is not None:
                try:
                    self._store_revision = self.store.save(
                        after, expected_revision=self._store_revision
                    )
                except StateStoreError:
                    # SQLite is authoritative. An uncertain commit outcome must
                    # be resolved by reopening the database, not more mutations.
                    self._failed = True
                    raise

    def close(self):
        if self.store is not None:
            self.store.close()

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
            wording=self.wording_views.read(spec),
            stale_for_display=(
                session.settings != selected.offer.context_snapshot.settings
                or not episode_is_active(
                    self,
                    selected.offer,
                    allow_legacy=self.allow_legacy_adaptive_sessions,
                )
            ),
        )

    def accept_feedback(self, session_id, exposure_id, request):
        spec = self.presentation(session_id, exposure_id)
        if (
            request.presentation_id != spec.presentation_id
            or request.configuration_id != spec.configuration.configuration_id
            or request.decision_id != spec.decision_id
        ):
            raise HTTPException(409, "feedback presentation identity mismatch")

        origin = (
            "simulation"
            if self.policy_config.feedback_mode == "simulation"
            else "participant_report"
        )
        receipt = self.policy.apply_feedback(
            SupportFitFeedback(
                exposure_id=exposure_id,
                rating=request.rating,
                origin=origin,
            )
        )

        previous = self.feedback.get(exposure_id)
        if previous is not None:
            if previous.receipt != receipt:
                raise StateStoreError("feedback receipt differs from recorded result")
            return previous

        accepted = AcceptedFeedback(
            accepted_at=datetime.now(timezone.utc),
            receipt=receipt,
        )
        self.feedback[exposure_id] = accepted
        return accepted



def create_app(
    *,
    provider=None,
    graphs: tuple[CanonicalProcedureGraph, ...] | None = None,
    safety_by_fingerprint: dict[str, ContentSafety] | None = None,
    database_path: str | Path | None = None,
    policy_config: PolicyConfig | None = None,
    postgres_dsn: str | None = None,
    allow_legacy_adaptive_sessions: bool = True,
    content_directory: str | Path | None = None,
    reviewed_content_only: bool = False,
    prepared_wording_directory: str | Path | None = None,
    wording_views_directory: str | Path | None = None,
) -> FastAPI:
    """Create the independent C4 research application.

    Factory-created applications default to in-memory state for tests.
    The module-level application below explicitly enables SQLite.

    LLM calls remain disabled unless C4_DEV_LLM_ENABLED=true.

    The factory retains legacy unprofiled research sessions for existing
    experiments/tests. The environment-created server explicitly sets
    allow_legacy_adaptive_sessions=False. Disabled profiles are rejected
    regardless of this compatibility option.
    """
    if type(allow_legacy_adaptive_sessions) is not bool:
        raise TypeError("allow_legacy_adaptive_sessions must be bool")

    @asynccontextmanager
    async def lifespan(application):
        active_provider = provider
        owns_provider = active_provider is None
        generation_enabled = True

        if active_provider is None:
            enabled = os.getenv("C4_DEV_LLM_ENABLED", "false").lower()
            if enabled not in {"true", "false"}:
                raise ValueError("C4_DEV_LLM_ENABLED must be true or false")

            active_provider = OpenAIExplanationProvider.from_environment(
                allow_live=enabled == "true"
            )
            generation_enabled = (
                enabled == "true"
                and os.getenv("C4_LLM_ENABLED", "true").lower() == "true"
            )

        active_runtime = None
        try:
            if graphs is None:
                active_graphs, catalogue_safety = load_demo_procedures()
            else:
                active_graphs = graphs
                catalogue_safety = {}

            active_safety = (
                catalogue_safety
                if safety_by_fingerprint is None
                else safety_by_fingerprint
            )

            active_runtime = DevRuntime(
                active_provider,
                active_graphs,
                active_safety,
                database_path=database_path,
                policy_config=policy_config,
                postgres_dsn=postgres_dsn,
                allow_legacy_adaptive_sessions=allow_legacy_adaptive_sessions,
                content_directory=content_directory,
                reviewed_content_only=reviewed_content_only,
                generation_enabled=generation_enabled,
                prepared_wording_directory=prepared_wording_directory,
                wording_views_directory=wording_views_directory,
            )
            application.state.runtime = active_runtime
            yield
        finally:
            if active_runtime is not None:
                active_runtime.close()
            if owns_provider:
                active_provider.close()


    application = FastAPI(
        title="HelaGuide C4 Independent Research API",
        version="0.5.0",
        lifespan=lifespan,
        description=(
            "Local research prototype. Sources may be synthetic. "
            "Presentation creation is not exposure acknowledgment. "
            "Explicit support-fit feedback can update the shared policy. "
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
        value = application.state.runtime
        value.assert_available()
        return value

    register_demo_profile_routes(application, runtime)

    @application.exception_handler(StateStoreError)
    async def storage_failure(request, exc):
        return JSONResponse(
            status_code=503,
            content={
                "detail": {
                    "code": "state_store_unavailable",
                    "message": (
                        "State could not be safely committed or recovered. "
                        "Restart the development server and inspect its startup error."
                    ),
                }
            },
        )

    @application.get("/health")
    def health():
        return {
            "service": "c4-independent-dev",
            "status": "ok",
            "storage": runtime().storage_backend,
            "exposure_requires_acknowledgment": True,
            "content": {
                "persistent_artifacts": runtime().explanations.artifact_store is not None,
                "reviewed_only": runtime().explanations.reviewed_only,
                "generation_enabled": runtime().explanations.generation_enabled,
            },
        }

    @application.get("/dev/v1/procedures")
    def procedures():
        with runtime().lock:
            return [
                {
                    "procedure_id": fingerprint,
                    "plan_id": graph.plan_id,
                    "title": next(
                        stage.name
                        for stage in graph.stages
                        if stage.service_id == graph.requested_service_id
                    ),
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


    @application.get(
        "/dev/v1/procedures/{procedure_id}/graph",
        response_model=CanonicalProcedureGraph,
    )
    def procedure_graph(procedure_id: str):
        current = runtime()
        with current.lock:
            graph, _, _ = current.procedure(procedure_id)
            return graph

    @application.get(
        "/dev/v1/sessions/{session_id}/history",
        response_model=SessionHistoryResponse,
    )
    def session_history(session_id: str):
        current = runtime()
        with current.lock:
            session = current.session(session_id)
            return SessionHistoryResponse(
                session=session,
                events=current.contexts.event_history(session_id),
            )

    @application.post(
        "/dev/v1/sessions",
        response_model=GuestSession,
        status_code=201,
    )
    def create_session():
        with runtime().change():
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
        with runtime().change():
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
                session_id,
                graph,
                features,
                safety=safety,
            )

    @application.post(
        "/dev/v1/sessions/{session_id}/presentations",
        response_model=PresentationResponse,
        status_code=201,
    )
    def create_presentation(session_id: str, request: PresentationRequest):
        with runtime().change():
            require_personalization(
                runtime(),
                session_id,
                allow_legacy=runtime().allow_legacy_adaptive_sessions,
            )
            session = runtime().session(session_id)
            if request.expected_revision != session.revision:
                raise HTTPException(409, "session revision changed")

            graph, features, safety = runtime().procedure(request.procedure_id)
            familiarity = session.settings.familiarity_for(graph.requested_service_id)
            navigation = session.settings.navigation_capability
            writing_style = (
                "plain" if familiarity is None or navigation is None else
                "extra_plain" if familiarity <= 2 or navigation <= 2 else
                "concise" if familiarity >= 4 and navigation >= 4 else "plain"
            )
            prepared_wording = runtime().wording_views.prepare(graph, writing_style=writing_style)
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
                    session_id,
                    graph,
                    features,
                    safety=safety,
                )
                raise HTTPException(
                    409,
                    detail={
                        "code": "no_feasible_configuration",
                        "message": (
                            "Review explicit locks and accessibility constraints."
                        ),
                        "evaluation": evaluation.model_dump(mode="json"),
                    },
                ) from None
            except ContextConflictError as exc:
                raise HTTPException(409, str(exc)) from None

            result = runtime().explanations.explain(
                graph,
                selected,
                safety=safety,
            )
            spec = build_presentation_spec(
                graph,
                selected,
                result,
                focus_action_id=request.focus_action_id,
                safety=safety,
            )
            runtime().presentations[spec.exposure_id] = spec
            runtime().wording_views.capture(spec, prepared_wording, writing_style=writing_style)
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
        with runtime().change():
            spec = runtime().presentation(session_id, exposure_id)
            if (
                request.presentation_id != spec.presentation_id
                or request.configuration_id
                != spec.configuration.configuration_id
            ):
                raise HTTPException(409, "presentation identity mismatch")

            displayed = tuple(request.displayed_action_ids)
            if (
                len(displayed) != len(set(displayed))
                or not set(displayed) <= set(spec.acknowledgment_action_ids)
            ):
                raise HTTPException(
                    422,
                    "displayed actions are outside this presentation's "
                    "acknowledgment scope",
                )

            already_acknowledged = any(
                isinstance(event, PresentationExposure)
                and event.offer.exposure_id == exposure_id
                for event in runtime().contexts.event_history(session_id)
            )
            if not already_acknowledged:
                selected = runtime().policy.get_offer(exposure_id)
                require_active_episode(
                    runtime(),
                    selected.offer,
                    allow_legacy=runtime().allow_legacy_adaptive_sessions,
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
    

    @application.get(
        "/dev/v1/sessions/{session_id}/presentations/{exposure_id}/navigation",
        response_model=NavigationResponse,
    )
    def navigation_state(session_id: str, exposure_id: str):
        current = runtime()
        with current.lock:
            spec = current.presentation(session_id, exposure_id)
            session = current.session(session_id)
            history = current.contexts.event_history(session_id)

            acknowledgment = next(
                (
                    event
                    for event in history
                    if isinstance(event, PresentationExposure)
                    and event.offer.exposure_id == exposure_id
                ),
                None,
            )
            events = tuple(
                event
                for event in history
                if isinstance(event, ActionDisplay)
                and event.exposure_id == exposure_id
            )

            displayed = {}
            current_action = None
            if acknowledgment is not None:
                for action_id in acknowledgment.displayed_action_ids:
                    displayed[action_id] = None
                    current_action = action_id

            for event in events:
                displayed.pop(event.action_id, None)
                displayed[event.action_id] = None
                current_action = event.action_id

            return NavigationResponse(
                presentation_id=spec.presentation_id,
                exposure_id=exposure_id,
                configuration_id=spec.configuration.configuration_id,
                graph_fingerprint=spec.graph_fingerprint,
                session_revision=session.revision,
                acknowledged=acknowledgment is not None,
                current_action_id=current_action,
                displayed_action_ids=tuple(displayed),
                events=events,
            )

    @application.post(
        "/dev/v1/sessions/{session_id}/presentations/{exposure_id}/navigation",
        response_model=ActionDisplay,
    )
    def record_navigation(
        session_id: str,
        exposure_id: str,
        request: ActionDisplayRequest,
    ):
        current = runtime()
        with current.change():
            spec = current.presentation(session_id, exposure_id)
            if (
                request.presentation_id != spec.presentation_id
                or request.configuration_id
                != spec.configuration.configuration_id
            ):
                raise HTTPException(409, "presentation identity mismatch")

            if request.action_id not in {
                page.action_id for page in spec.pages
            }:
                raise HTTPException(422, "action is outside this presentation")

            existing_event = any(
                isinstance(event, ActionDisplay)
                and event.event_id == request.event_id
                for event in current.contexts.event_history(session_id)
            )
            if not existing_event:
                selected = current.policy.get_offer(exposure_id)
                require_active_episode(
                    current,
                    selected.offer,
                    allow_legacy=current.allow_legacy_adaptive_sessions,
                )

            try:
                return current.contexts.record_action_display(
                    session_id,
                    exposure_id,
                    event_id=request.event_id,
                    presentation_id=request.presentation_id,
                    configuration_id=request.configuration_id,
                    action_id=request.action_id,
                    expected_revision=request.expected_revision,
                )
            except ContextConflictError as exc:
                raise HTTPException(409, str(exc)) from None
            except ContextError as exc:
                raise HTTPException(422, str(exc)) from None


    @application.post(
        "/dev/v1/sessions/{session_id}/presentations/{exposure_id}/feedback",
        response_model=AcceptedFeedback,
    )
    def submit_feedback(
        session_id: str,
        exposure_id: str,
        request: FeedbackRequest,
    ):
        with runtime().change():
            try:
                return runtime().accept_feedback(
                    session_id,
                    exposure_id,
                    request,
                )
            except FeedbackConflictError as exc:
                raise HTTPException(409, str(exc)) from None
            except PolicyError as exc:
                raise HTTPException(409, str(exc)) from None

    @application.get(
        "/dev/v1/sessions/{session_id}/presentations/{exposure_id}/feedback",
        response_model=AcceptedFeedback,
    )
    def get_feedback(session_id: str, exposure_id: str):
        with runtime().lock:
            runtime().presentation(session_id, exposure_id)
            accepted = runtime().feedback.get(exposure_id)
            if accepted is None:
                raise HTTPException(404, "no accepted support-fit feedback")
            return accepted



    @application.get(
        "/dev/v1/sessions/{session_id}/presentations/{exposure_id}/correction-options",
        response_model=CorrectionOptions,
    )
    def get_correction_options(
        session_id: str,
        exposure_id: str,
    ):
        current = runtime()
        with current.lock:
            spec = current.presentation(session_id, exposure_id)
            return correction_options(current, spec)

    @application.post(
        "/dev/v1/sessions/{session_id}/presentations/{exposure_id}/correction",
        response_model=CorrectionRecord,
    )
    def submit_correction(
        session_id: str,
        exposure_id: str,
        request: CorrectionRequest,
    ):
        current = runtime()
        with current.change():
            spec = current.presentation(session_id, exposure_id)
            return record_correction(current, spec, request)

    @application.get(
        "/dev/v1/sessions/{session_id}/presentations/{exposure_id}/correction",
        response_model=CorrectionRecord,
    )
    def get_correction(
        session_id: str,
        exposure_id: str,
    ):
        current = runtime()
        with current.lock:
            current.presentation(session_id, exposure_id)
            record = current.corrections.get(exposure_id)
            if record is None:
                raise HTTPException(404, "no recorded correction")
            return record

    @application.post(
        "/dev/v1/sessions/{session_id}/presentations/{exposure_id}/correction/apply",
        response_model=CorrectionRecord,
    )
    def apply_recorded_correction(
        session_id: str,
        exposure_id: str,
        request: ApplyCorrectionRequest,
    ):
        current = runtime()
        with current.change():
            spec = current.presentation(session_id, exposure_id)
            return apply_correction(current, spec, request)


    @application.get("/dev/v1/policy")
    def policy_status():
        with runtime().lock:
            policy = runtime().policy
            from app.core.prior import prior_digest
            return {
                "policy_run_id": policy.policy_run_id,
                "model_version": policy.config.model_version,
                "feedback_mode": policy.config.feedback_mode,
                "prior_version": policy.config.prior.version if policy.config.prior else "neutral",
                "prior_status": policy.config.prior.status if policy.config.prior else "neutral",
                "prior_digest": prior_digest(policy.config.prior),
                "cold_start_updates": policy.config.cold_start_updates,
                "feature_schema_version": FEATURE_SCHEMA_VERSION,
                "feature_schema_fingerprint": FEATURE_SCHEMA_FINGERPRINT,
                "feature_dimension": FEATURE_DIMENSION,
                "posterior_revision": policy.posterior_revision,
                "posterior_fingerprint": policy.posterior_fingerprint(),
                "accepted_feedback_count": len(runtime().feedback),
                "storage": runtime().storage_backend,
            }

    register_guidance_routes(application, runtime, create_presentation)
    return application


def _application_from_environment():
    # Load C4's local file before evaluating either the live gate or storage.
    # Existing shell variables take precedence. Never load the team's root .env.
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    review_mode = os.getenv("C4_REVIEWED_CONTENT_ONLY", "true").lower()
    if review_mode not in {"true", "false"}:
        raise ValueError("C4_REVIEWED_CONTENT_ONLY must be true or false")
    content_directory = os.getenv("C4_CONTENT_DIR") or (
        Path(__file__).resolve().parents[1] / ".local" / "wording-artifacts"
    )
    mode = os.getenv("C4_FEEDBACK_MODE", "simulation").lower()
    if mode not in {"simulation", "participant"}:
        raise ValueError("C4_FEEDBACK_MODE must be simulation or participant")

    backend = os.getenv("C4_STORAGE_BACKEND", "sqlite").lower()
    if backend not in {"sqlite", "postgresql"}:
        raise ValueError("C4_STORAGE_BACKEND must be sqlite or postgresql")

    # Explicit opt-in; an absent file setting is a neutral prior. A bad supplied
    # file fails closed instead of silently changing the model at startup.
    from app.core.prior import load_prior
    prior_path = os.getenv("C4_PRIOR_FILE")
    config = PolicyConfig(feedback_mode=mode, cold_start_updates=0,
                          prior=load_prior(prior_path) if prior_path else None)
    prepared_wording_directory = os.getenv("C4_PREPARED_WORDING_DIR") or (
        Path(__file__).resolve().parents[1] / ".local" / "prepared-wording"
    )
    wording_views_directory = os.getenv("C4_WORDING_VIEWS_DIR") or (
        Path(__file__).resolve().parents[1] / ".local" / "wording-views" / mode
    )

    if backend == "postgresql":
        dsn = os.getenv("C4_DATABASE_URL")
        if not dsn or not dsn.strip():
            raise ValueError(
                "C4_DATABASE_URL is required for PostgreSQL storage"
            )
        return create_app(
            postgres_dsn=dsn,
            policy_config=config,
            allow_legacy_adaptive_sessions=False,
            content_directory=content_directory,
            reviewed_content_only=review_mode == "true",
            prepared_wording_directory=prepared_wording_directory,
            wording_views_directory=wording_views_directory,
        )

    default_path = (
        Path(__file__).resolve().parents[1]
        / ".local"
        / f"c4-{mode}.sqlite3"
    )
    database_path = os.getenv("C4_STATE_DB") or default_path

    return create_app(
        database_path=database_path,
        policy_config=config,
        allow_legacy_adaptive_sessions=False,
        content_directory=content_directory,
        reviewed_content_only=review_mode == "true",
        prepared_wording_directory=prepared_wording_directory,
        wording_views_directory=wording_views_directory,
    )


app = _application_from_environment()
