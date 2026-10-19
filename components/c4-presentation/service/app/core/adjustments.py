"""Bounded manual views; never resample LinTS or treat an override as its reward."""
from datetime import datetime, timezone
from fastapi import HTTPException
from app.core.presentation import build_source_cards, diagram_for_configuration, item
from app.core.state_store import StateStoreError
from app.models.adjustments import AdjustmentState, ViewRecord, ViewDisplay, ViewRating
from app.models.presentation import PresentationSpec, Recap
from app.models.scaffolds import VisibilityDeclaration


ROOT = "original"
def now():
    return datetime.now(timezone.utc)

def current_id(ledger):
    return ledger.views[-1].view_id if ledger.views else ROOT

def stack(ledger):
    result = [ROOT]
    for view in ledger.views:
        if view.parent_view_id != result[-1] or view.view_id in result:
            raise StateStoreError("invalid adjustment lineage")
        if view.operation == "adjust":
            result.append(view.view_id)
        else:
            if len(result) < 2:
                raise StateStoreError("invalid adjustment undo")
            result.pop()
            if view.undo_target_id != result[-1]:
                raise StateStoreError("invalid undo target")
            # Keep the new display identity, with the restored target's ancestry.
            result[-1] = view.view_id
    return result

def original_configuration(ledger, root):
    return not ledger.views or ledger.views[-1].configuration == root.configuration

def compose(root, selected, configuration, focus):
    """Recompose only layout fields; source text and original wording stay frozen."""
    graph = root.explanation.source.graph
    feasibility = selected.decision.evaluation.feasibility
    cards = build_source_cards(graph, root.explanation.source, configuration)
    pages = []
    for page in root.pages:
        cues = []
        if configuration.prerequisite_cue:
            if "stage" in feasibility.supported_dependency_layers:
                cues.extend(item("stage_dependency", edge.edge_id) for edge in graph.stage_dependencies if edge.target_id == page.service_id)
            if "action" in feasibility.supported_dependency_layers:
                cues.extend(item("action_prerequisite", edge.edge_id) for edge in graph.action_prerequisites if edge.target_id == page.action_id)
        pages.append(page.model_copy(update={"prerequisite_cues": tuple(cues)}))
    snapshot = selected.offer.context_snapshot
    recap = Recap(action_ids=snapshot.recap_action_ids, exposure_ids=tuple(e.exposure_id for e in snapshot.recent_exposures if e.displayed_action_ids)) if configuration.previous_context_recap else None
    values = root.model_dump()
    values.update(configuration=configuration, explanation=root.explanation.model_copy(update={"configuration": configuration}),
                  cards=cards, pages=tuple(pages), initial_action_id=focus if configuration.presentation_mode == "GUIDED" else None,
                  diagram=diagram_for_configuration(graph, configuration, feasibility), recap=recap,
                  visibility=VisibilityDeclaration(visible=tuple(c.source for c in cards if not c.collapsed), collapsed=tuple(c.source for c in cards if c.collapsed)),
                  acknowledgment_action_ids=(focus,) if configuration.presentation_mode == "GUIDED" else tuple(p.action_id for p in pages))
    # Root IDs remain policy lineage, not a new policy offer. view_id identifies manual displays.
    return PresentationSpec.model_validate(values)

def read(runtime, root):
    selected = runtime.policy.get_offer(root.exposure_id)
    ledger = runtime.adjustments.read(root, selected.decision.policy_run_id)
    candidates = selected.decision.evaluation.feasibility.feasible_candidates()
    ids = {ROOT}
    configurations = {ROOT: root.configuration}
    for view in ledger.views:
        if view.view_id in ids or view.parent_view_id not in ids or view.configuration not in candidates or view.focus_action_id not in {p.action_id for p in root.pages}:
            raise StateStoreError("adjusted view differs from original feasible scope")
        ids.add(view.view_id)
        if view.operation == "undo" and (view.undo_target_id not in configurations or view.configuration != configurations[view.undo_target_id]):
            raise StateStoreError("undo configuration differs from target")
        configurations[view.view_id] = view.configuration
    stack(ledger)
    if ledger.revision != len(ledger.views) + len(ledger.displays) + len(ledger.ratings):
        raise StateStoreError("adjustment revision differs from history")
    if sorted(e.expected_revision for e in (*ledger.views, *ledger.displays, *ledger.ratings)) != list(range(ledger.revision)):
        raise StateStoreError("adjustment event revisions are inconsistent")
    event_ids = [e.event_id for e in (*ledger.displays, *ledger.ratings)]
    if len(event_ids) != len(set(event_ids)) or any(e.view_id not in ids - {ROOT} for e in (*ledger.displays, *ledger.ratings)):
        raise StateStoreError("invalid adjustment event attribution")
    if any(d.action_id not in {p.action_id for p in root.pages} for d in ledger.displays):
        raise StateStoreError("manual display action is outside the source graph")
    if len({r.view_id for r in ledger.ratings}) != len(ledger.ratings) or any(not any(d.view_id == r.view_id and d.recorded_at <= r.recorded_at for d in ledger.displays) for r in ledger.ratings):
        raise StateStoreError("adjustment rating lacks displayed view")
    return ledger

def state(runtime, root, ledger=None):
    selected = runtime.policy.get_offer(root.exposure_id)
    ledger = read(runtime, root) if ledger is None else ledger
    view = ledger.views[-1] if ledger.views else None
    focus = view.focus_action_id if view else root.initial_action_id or root.pages[0].action_id
    original = original_configuration(ledger, root)
    spec = root if view is None else compose(root, selected, view.configuration, focus)
    return AdjustmentState(ledger=ledger, active_view_id=current_id(ledger), original_view=original, spec=spec, focus_action_id=focus,
        displayed_action_ids=tuple(dict.fromkeys(d.action_id for d in ledger.displays if d.view_id == current_id(ledger))),
        feasible_configurations=selected.decision.evaluation.feasibility.feasible_candidates(), can_undo=len(stack(ledger)) > 1,
        stale_for_display=runtime.response(root).stale_for_display,
        learning_eligible=not ledger.views)

def require_current(runtime, root, ledger, expected):
    if ledger.revision != expected:
        raise HTTPException(409, "view history changed; refresh before making another change")
    if runtime.response(root).stale_for_display:
        raise HTTPException(409, "settings or routing changed; request fresh guidance")

def adjust(runtime, root, request):
    ledger = read(runtime, root)
    vid = "view:" + request.request_id.split(":")[1]
    previous = next((v for v in ledger.views if v.view_id == vid), None)
    if previous:
        if previous.expected_revision != request.expected_revision or previous.parent_view_id != request.parent_view_id or previous.operation != request.operation or previous.focus_action_id != request.focus_action_id or (request.operation == "undo" and request.configuration is not None) or (request.operation == "adjust" and previous.configuration != request.configuration):
            raise HTTPException(409, "adjustment request identity reused with different data")
        return state(runtime, root, ledger)
    require_current(runtime, root, ledger, request.expected_revision)
    if request.parent_view_id != current_id(ledger):
        raise HTTPException(409, "parent view changed")
    if request.focus_action_id not in {p.action_id for p in root.pages}:
        raise HTTPException(422, "unknown focus action")
    if len(ledger.views) >= 100:
        raise HTTPException(409, "view history limit reached; request fresh guidance")
    target = None
    if request.operation == "undo":
        if request.configuration is not None:
            raise HTTPException(422, "Undo does not accept a configuration")
        history = stack(ledger)
        if len(history) < 2:
            raise HTTPException(409, "no adjustment to undo")
        target = history[-2]
        config = root.configuration if target == ROOT else next(v.configuration for v in ledger.views if v.view_id == target)
    else:
        config = request.configuration
        selected = runtime.policy.get_offer(root.exposure_id)
        if config is None or config not in selected.decision.evaluation.feasibility.feasible_candidates():
            raise HTTPException(409, "requested view is not feasible under original structure, content review, accessibility and hard locks")
        active_config = ledger.views[-1].configuration if ledger.views else root.configuration
        if config == active_config:
            raise HTTPException(409, "configuration is already displayed")
    view = ViewRecord(expected_revision=request.expected_revision, view_id=vid, parent_view_id=current_id(ledger), operation=request.operation, configuration=config,
                      focus_action_id=request.focus_action_id, created_at=now(), undo_target_id=target)
    updated = ledger.model_copy(update={"views": ledger.views + (view,), "revision": ledger.revision + 1})
    # Validate source preservation before committing the new view.
    response = state(runtime, root, updated)
    runtime.adjustments.save(root, updated)
    return response

def display(runtime, root, request):
    ledger = read(runtime, root)
    previous = next((e for e in ledger.displays if e.event_id == request.event_id), None)
    if previous:
        if (previous.view_id, previous.action_id, previous.expected_revision) != (request.view_id, request.action_id, request.expected_revision):
            raise HTTPException(409, "display identity reused")
        return state(runtime, root, ledger)
    require_current(runtime, root, ledger, request.expected_revision)
    if not ledger.views or request.view_id != current_id(ledger) or request.action_id not in {p.action_id for p in root.pages}:
        raise HTTPException(409, "display does not match the active adjusted view")
    if any(e.event_id == request.event_id for e in ledger.ratings):
        raise HTTPException(409, "event identity already used")
    active = state(runtime, root, ledger)
    if not active.displayed_action_ids and request.action_id not in active.spec.acknowledgment_action_ids:
        raise HTTPException(422, "initial display is outside this view's acknowledgment scope")
    event = ViewDisplay(expected_revision=request.expected_revision, event_id=request.event_id, view_id=request.view_id, action_id=request.action_id, recorded_at=now())
    updated = ledger.model_copy(update={"displays": ledger.displays + (event,), "revision": ledger.revision + 1})
    runtime.adjustments.save(root, updated)
    return state(runtime, root, updated)

def rate(runtime, root, request):
    ledger = read(runtime, root)
    existing = next((r for r in ledger.ratings if r.view_id == request.view_id), None)
    if existing:
        if existing.event_id != request.event_id or existing.rating != request.rating or existing.expected_revision != request.expected_revision:
            raise HTTPException(409, "a rating was already saved for this view")
        return state(runtime, root, ledger)
    require_current(runtime, root, ledger, request.expected_revision)
    if request.view_id != current_id(ledger) or not any(d.view_id == request.view_id for d in ledger.displays):
        raise HTTPException(409, "view must be acknowledged as displayed before rating")
    if any(e.event_id == request.event_id for e in (*ledger.displays, *ledger.ratings)):
        raise HTTPException(409, "event identity already used")
    event = ViewRating(expected_revision=request.expected_revision, event_id=request.event_id, view_id=request.view_id, rating=request.rating, recorded_at=now(),
                       origin="simulation" if runtime.policy_config.feedback_mode == "simulation" else "participant_report")
    updated = ledger.model_copy(update={"ratings": ledger.ratings + (event,), "revision": ledger.revision + 1})
    runtime.adjustments.save(root, updated)
    return state(runtime, root, updated)

def require_original_feedback(runtime, root):
    # Once an episode has manual-view lineage, even Undo ratings stay separate.
    # This avoids treating post-intervention feedback as an original-policy outcome.
    if read(runtime, root).views and root.exposure_id not in runtime.feedback:
        raise HTTPException(409, "this episode has manual views; rate the displayed view separately or request fresh guidance for policy feedback")

def require_original_display(runtime, root):
    if read(runtime, root).views:
        raise HTTPException(409, "record manual-view display through the view endpoint")
