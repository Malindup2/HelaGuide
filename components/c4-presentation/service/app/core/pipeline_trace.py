"""Project stored records without evaluating feasibility, selecting, generating or writing."""

from app.core.guidance_access import episode_is_active, guidance_status
from app.core.policy import CONTEXT_NAMES, FEATURE_NAMES_SHARED, encode_context
from app.core.prior import prior_digest
from app.core.scaffolds import graph_fingerprint
from app.core.state_store import StateStoreError
from app.models.pipeline_trace import (
    ContentSummary, CurrentTraceStatus, DisplaySummary, EvidenceBoundary, FeedbackSummary,
    InputSummary, PipelineTrace, PipelineTraceIndex, RecordedTrace, SelectionSummary,
    TraceCandidate, TraceFeature, TraceListEntry,
)
from app.models.procedure_features import FEATURE_NAMES
from app.models.user_context import ActionDisplay, PresentationExposure


def boundary(section, kind, location, explanation):
    return EvidenceBoundary(section=section, kind=kind, location=location, explanation=explanation)


BOUNDARIES = (
    boundary("input", "recorded", "records.presentation.explanation.source.graph",
             "Saved canonical graph, supplied provenance and evidence. Source dates are not validation timestamps."),
    boundary("input", "unavailable", "input.raw_plan_payload",
             "Original raw Plan/enrichment payloads and historical validation execution events were not stored."),
    boundary("features", "recorded", "records.policy_offer.decision.structural_features",
             "Original source-based measurements used at selection; generated wording does not change them."),
    boundary("content", "recorded", "records.presentation.explanation; records.wording; records.wording_artifact",
             "Original explanation and available frozen wording snapshot, not today's prepared-content registry. Provider-call metadata belongs to artifact creation and does not prove a live call for this view."),
    boundary("context", "recorded", "records.policy_offer.offer.context_snapshot",
             "Settings and processed history at selection, distinct from current profile/context state."),
    boundary("feasibility", "recorded", "records.policy_offer.decision.evaluation.feasibility",
             "Original acceptance/rejection reasons. Rejected candidates were not scored."),
    boundary("selection", "recorded", "records.policy_offer.decision",
             "Original prior, scores, uncertainty, sampled parameters and seed; no policy resampling occurs on a trace read."),
    boundary("presentation", "recorded", "records.presentation",
             "Declared source cards, layout, diagram and recap. A declaration alone does not establish display."),
    boundary("display", "recorded", "records.acknowledgment; records.navigation_events",
             "Client display acknowledgments, not proof of reading, comprehension, eligibility or completion."),
    boundary("feedback", "recorded", "records.feedback; records.correction",
             "Accepted rating and receipt are separate from optional diagnostic reasons and preference application."),
    boundary("summaries", "derived", "input; structural_features; content; candidates; selection; display; learning",
             "Counts, labels, named encoding, score joins and update deltas are calculated from the recorded fields. No causal feature-importance explanation is claimed."),
    boundary("current", "derived", "current",
             "Current session and shared-model state observed under the runtime lock; not historical state at selection or feedback acceptance."),
    boundary("feedback", "unavailable", "learning.historical_post_update_parameters",
             "The receipt records the resulting revision, not a separately saved parameter snapshot immediately after that update."),
)


def exposure_records(runtime, session_id, exposure_id):
    history = runtime.contexts.event_history(session_id)
    ack = next((e for e in history if isinstance(e, PresentationExposure)
                and e.offer.exposure_id == exposure_id), None)
    events = tuple(e for e in history if isinstance(e, ActionDisplay) and e.exposure_id == exposure_id)
    return ack, events


def build_pipeline_trace(runtime, session_id, exposure_id):
    spec = runtime.presentation(session_id, exposure_id)  # checks session ownership first
    selected = runtime.policy.get_offer(exposure_id)
    decision, offer = selected.decision, selected.offer
    graph = spec.explanation.source.graph
    if (spec.decision_id != decision.decision_id or offer.session_id != session_id
        or spec.configuration != offer.configuration or spec.graph_fingerprint != offer.graph_fingerprint
        or graph_fingerprint(graph) != spec.graph_fingerprint):
        raise StateStoreError("pipeline trace records have inconsistent attribution")

    feasibility = decision.evaluation.feasibility
    scores = {s.configuration.configuration_id: s for s in decision.candidate_scores}
    feasible_ids = {c.configuration_id for c in feasibility.feasible_candidates()}
    if len(scores) != len(decision.candidate_scores) or set(scores) != feasible_ids:
        raise StateStoreError("pipeline trace scores differ from recorded feasible candidates")
    candidates = tuple(TraceCandidate(
        configuration=c.configuration, feasible=c.accepted,
        selected=c.configuration == decision.configuration,
        satisfied=c.satisfied, rejections=c.rejections,
        score_status=("not_scored" if not c.accepted else
                      "recorded_moments_not_sampled" if scores[c.configuration.configuration_id].sampled_score is None
                      else "recorded_thompson_score"),
        score=scores.get(c.configuration.configuration_id),
    ) for c in feasibility.decisions)

    ack, events = exposure_records(runtime, session_id, exposure_id)
    displayed = dict.fromkeys(ack.displayed_action_ids if ack else ())
    current_action = ack.displayed_action_ids[-1] if ack and ack.displayed_action_ids else None
    for event in events:
        displayed.pop(event.action_id, None)
        displayed[event.action_id] = None
        current_action = event.action_id

    accepted = runtime.feedback.get(exposure_id)
    receipt = accepted.receipt if accepted else None
    if receipt is not None and (receipt.policy_run_id != decision.policy_run_id
                                or receipt.decision_id != decision.decision_id
                                or receipt.feedback.exposure_id != exposure_id):
        raise StateStoreError("pipeline trace feedback attribution differs")
    variance = decision.config.observation_noise ** 2
    centered = receipt.reward - 0.5 if receipt else None
    session = runtime.session(session_id)
    wording_view = runtime.wording_views.read_view(spec)  # validates only the original sidecar
    wording = wording_view.wording if wording_view else None
    explanation = spec.explanation
    return PipelineTrace(
        records=RecordedTrace(policy_offer=selected, presentation=spec, wording=wording,
                              wording_artifact=wording_view.artifact if wording_view else None,
                              wording_style=wording_view.writing_style if wording_view else None,
                              acknowledgment=ack, navigation_events=events, feedback=accepted,
                              correction=runtime.corrections.get(exposure_id)),
        input=InputSummary(graph_fingerprint=spec.graph_fingerprint, fingerprint_matches_saved_graph=True,
                           source_authenticity=explanation.source_status,
                           graph_counts={name: len(getattr(graph, name)) for name in (
                               "stages", "actions", "stage_dependencies", "action_prerequisites", "conditions",
                               "branch_groups", "parallel_groups", "content", "evidence", "facts", "provenance")}),
        structural_features=tuple(TraceFeature(name=name, measurement=getattr(decision.structural_features, name))
                                  for name in FEATURE_NAMES),
        content=ContentSummary(
            explanation_origin=explanation.origin, assurance=explanation.assurance,
            recorded_cache_hit=explanation.cache_hit, diagnostics=explanation.diagnostics,
            generated_item_count=sum(e.origin == "generated" for e in explanation.explanations),
            source_copy_item_count=sum(e.origin == "source_copy" for e in explanation.explanations),
            wording_status=("snapshot_not_available" if wording is None else
                            "reviewed_snapshot" if wording.artifact_digest else "snapshot_source_fallback"),
            wording_origins=tuple(sorted({item.origin for item in wording.items})) if wording else (),
            wording_diagnostics=wording.diagnostics if wording else (),
            wording_digest=wording.artifact_digest if wording else None),
        candidates=candidates,
        selection=SelectionSummary(
            policy_run_id=decision.policy_run_id,
            prior_version=decision.config.prior.version if decision.config.prior else "neutral",
            prior_status=decision.config.prior.status if decision.config.prior else "neutral",
            prior_digest=prior_digest(decision.config.prior), selection_mode=decision.selection_mode,
            selection_reason=decision.selection_reason, selection_posterior_revision=decision.posterior_revision,
            feasible_count=len(feasible_ids), rejected_count=len(candidates) - len(feasible_ids),
            sampled_candidate_count=sum(s.sampled_score is not None for s in scores.values()),
            feature_names=FEATURE_NAMES_SHARED,
            context_encoding=tuple(zip(CONTEXT_NAMES,
                encode_context(decision.structural_features, offer.context_snapshot)))),
        display=DisplaySummary(status="acknowledged" if ack else "not_acknowledged",
                               displayed_action_ids=tuple(displayed), current_action_id=current_action,
                               navigation_event_count=len(events)),
        learning=FeedbackSummary(
            status="accepted" if receipt else "no_accepted_feedback" if ack else "awaiting_display_acknowledgment",
            reward=receipt.reward if receipt else None,
            selection_posterior_revision=decision.posterior_revision,
            revision_immediately_before_update=receipt.resulting_posterior_revision - 1 if receipt else None,
            resulting_posterior_revision=receipt.resulting_posterior_revision if receipt else None,
            precision_rank_one_scale=1 / variance if receipt else None,
            centered_reward=centered,
            linear_delta_b=tuple(value * centered / variance for value in decision.selected_features) if receipt else None),
        current=CurrentTraceStatus(
            guidance=guidance_status(runtime, session_id), user_settings=session.settings,
            shared_policy_run_id=runtime.policy.policy_run_id,
            shared_posterior_revision=runtime.policy.posterior_revision,
            shared_posterior_fingerprint=runtime.policy.posterior_fingerprint(),
            accepted_feedback_count=len(runtime.feedback),
            stale_for_display=(session.settings != offer.context_snapshot.settings or not episode_is_active(
                runtime, offer, allow_legacy=runtime.allow_legacy_adaptive_sessions))),
        evidence_boundaries=BOUNDARIES,
    )


def build_trace_index(runtime, session_id):
    status = guidance_status(runtime, session_id)
    entries = []
    for spec in runtime.presentations.values():
        if spec.session_id != session_id:
            continue
        selected = runtime.policy.get_offer(spec.exposure_id)
        ack, _ = exposure_records(runtime, session_id, spec.exposure_id)
        entries.append(TraceListEntry(exposure_id=spec.exposure_id, presentation_id=spec.presentation_id,
                                     decision_id=spec.decision_id, graph_fingerprint=spec.graph_fingerprint,
                                     offered_at=selected.offer.offered_at, configuration=spec.configuration,
                                     selection_posterior_revision=selected.decision.posterior_revision,
                                     acknowledged=ack is not None, feedback_accepted=spec.exposure_id in runtime.feedback))
    return PipelineTraceIndex(current_guidance=status,
                              current_request_routing="adaptive" if status.personalization_enabled else "standard",
                              presentations=tuple(sorted(entries, key=lambda e: (e.offered_at, e.exposure_id))),
                              explanation="Current routing is separate from saved adaptive history. Standard guidance does not persist presentation, policy-decision, exposure or learning records; this endpoint does not reconstruct an unsaved standard view.")
