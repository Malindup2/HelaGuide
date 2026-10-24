"""Local reusable wording registry and bounded provider preparation.

Resolution is offline and read-only. Preparation and review are explicit
operator actions. Existing M1 presentation artifacts remain independent.
"""

from datetime import datetime, timezone
from pathlib import Path

from app.preparation.explanation_store import (
    ArtifactStoreError, ExplanationArtifactStore, parse_artifact_json,
)
from app.preparation.explanations import OutputRejected, _canonical, _parse
from app.preparation.prepared_wording import (
    ASSESSMENT_PROMPT, GENERATION_PROMPT, RECIPE_VERSION,
    prepare_wording_packet, provider_packet, validate_wording_artifact,
    validate_wording_assessment, validate_wording_draft, wording_digest, wording_key,
)
from app.models.explanations import HumanReview
from app.models.prepared_wording import (
    ResolvedWordingItem, WordingArtifact, WordingAssessment, WordingDraft,
    WordingResolution,
)


MAX_BATCH_TARGETS = 8
MAX_SOURCE_BYTES = 60_000
MAX_ASSESSMENT_BYTES = 100_000


class PreparedWordingStore:
    def __init__(self, directory: str | Path):
        self.files = ExplanationArtifactStore(directory)

    def read(self, key):
        text = self.files.read_text(key)
        if text is None:
            return None
        artifact = parse_artifact_json(WordingArtifact, text)
        if artifact.request_key != key:
            raise ArtifactStoreError("wording_filename_mismatch")
        validate_wording_artifact(artifact)
        return artifact

    def save(self, artifact, *, replace_pending=False):
        validate_wording_artifact(artifact)
        existing = self.read(artifact.request_key)
        if existing is not None:
            if existing == artifact:
                return
            if existing.review is not None or not replace_pending:
                raise ArtifactStoreError("wording_exists_review_or_explicit_replacement_required")
        self.files.write_text(artifact.request_key, artifact.model_dump_json(indent=2))

    def review(self, key, *, reviewer_reference):
        if not reviewer_reference.strip():
            raise ValueError("reviewer_reference must not be blank")
        artifact = self.read(key)
        if artifact is None:
            raise ArtifactStoreError("wording_not_found")
        if artifact.origin == "demo_mock":
            raise ArtifactStoreError("mock_must_be_replaced_by_an_authored_or_provider_artifact")
        reviewed = artifact.model_copy(update={"review": HumanReview(
            artifact_digest=wording_digest(artifact), reviewer_reference=reviewer_reference,
            reviewed_at=datetime.now(timezone.utc),
        )})
        # Only the explicit operator review command can make this transition.
        self.files.write_text(key, reviewed.model_dump_json(indent=2))
        return reviewed


def make_human_artifact(packet, draft, *, author_reference, allow_partial=False):
    validate_wording_draft(packet, draft, require_complete=not allow_partial)
    artifact = WordingArtifact(
        request_key=wording_key(packet), recipe_version=RECIPE_VERSION,
        created_at=datetime.now(timezone.utc), source=packet, origin="human_prepared",
        author_reference=author_reference, provider=None, generation_calls=(),
        assessment_calls=(), draft=draft, assessment=None,
    )
    validate_wording_artifact(artifact)
    return artifact


def human_template(packet, *, author_reference):
    """Empty editable text fields; this template is not an approved artifact."""
    evidence = {record.evidence_id: record for record in packet.graph.evidence}
    return {
        "source": packet.model_dump(mode="json"),
        "author_reference": author_reference,
        "draft": {"synthetic": packet.graph.synthetic, "items": [
            {"slot_id": target.slot_id, "text": "",
             "source_references": [item.model_dump(mode="json") for item in target.source_references],
             "citations": [
                 {"evidence_id": key, "quote": evidence[key].text[:4000]}
                 for key in target.evidence_ids
             ]}
            for target in packet.targets
        ]},
    }


def preparation_batches(packet):
    batches = []
    current = []
    for target in packet.targets:
        trial = current + [target]
        if (len(trial) > MAX_BATCH_TARGETS
            or len(_canonical(provider_packet(packet, trial)).encode("utf-8")) > MAX_SOURCE_BYTES):
            if not current:
                raise OutputRejected("wording_single_target_too_large")
            batches.append(tuple(current))
            current = [target]
            if len(_canonical(provider_packet(packet, current)).encode("utf-8")) > MAX_SOURCE_BYTES:
                raise OutputRejected("wording_single_target_too_large")
        else:
            current = trial
    if current:
        batches.append(tuple(current))
    return tuple(batches)


def generate_wording(packet, provider, *, max_batches=8):
    """Two structured calls per batch, no retries and no automatic approval.

    Determine the full bounded batch plan before any paid call. Nothing is
    persisted if a later batch fails. The caller saves only a validated result.
    """
    expected = prepare_wording_packet(packet.graph, writing_style=packet.writing_style)
    if packet != expected:
        raise OutputRejected("wording_source_manifest_changed")
    batches = preparation_batches(packet)
    if not batches or len(batches) > max_batches:
        raise OutputRejected("wording_batch_budget_exceeded")
    items, assessments, generation_calls, assessment_calls = [], [], [], []
    for targets in batches:
        supplied = provider_packet(packet, targets)
        generated = provider.complete(
            instructions=GENERATION_PROMPT, payload=_canonical(supplied),
            response_model=WordingDraft,
        )
        draft = _parse(WordingDraft, generated.text)
        validate_wording_draft(packet, draft, targets=targets, require_complete=True)
        assessment_payload = _canonical({
            "source_packet": supplied, "proposed_wording": draft.model_dump(mode="json"),
        })
        if len(assessment_payload.encode("utf-8")) > MAX_ASSESSMENT_BYTES:
            raise OutputRejected("wording_assessment_packet_too_large")
        assessed = provider.complete(
            instructions=ASSESSMENT_PROMPT, payload=assessment_payload,
            response_model=WordingAssessment,
        )
        assessment = _parse(WordingAssessment, assessed.text)
        validate_wording_assessment(draft, assessment)
        items.extend(draft.items)
        assessments.extend(assessment.items)
        generation_calls.append(generated.call)
        assessment_calls.append(assessed.call)
    artifact = WordingArtifact(
        request_key=wording_key(packet), recipe_version=RECIPE_VERSION,
        created_at=datetime.now(timezone.utc), source=packet, origin="provider_generated",
        author_reference=None, provider=provider.identity,
        generation_calls=tuple(generation_calls), assessment_calls=tuple(assessment_calls),
        draft=WordingDraft(synthetic=packet.graph.synthetic, items=tuple(items)),
        assessment=WordingAssessment(items=tuple(assessments)),
    )
    validate_wording_artifact(artifact)
    return artifact


def resolve_wording(graph, store, *, writing_style="plain", allow_demo_mock=False):
    """Read only. Always expose source fallbacks for missing slots."""
    packet = prepare_wording_packet(graph, writing_style=writing_style)
    key = wording_key(packet)
    diagnostics = []
    artifact = None
    try:
        artifact = store.read(key)
        if artifact is not None:
            validate_wording_artifact(artifact)
        if artifact is None:
            diagnostics.append("wording_not_prepared")
        elif artifact.source != packet:
            raise OutputRejected("wording_current_source_mismatch")
        elif artifact.origin == "demo_mock" and allow_demo_mock:
            diagnostics.append("demo_mock_not_expert_reviewed_or_live_provider_output")
        elif artifact.review is None:
            diagnostics.append("wording_human_review_required")
            artifact = None
    except (ArtifactStoreError, OutputRejected) as exc:
        diagnostics.append(str(exc))
        artifact = None
    prepared = {} if artifact is None else {item.slot_id: item for item in artifact.draft.items}
    if artifact is not None and len(prepared) < len(packet.targets):
        diagnostics.append("wording_partial_source_fallback")
    return WordingResolution(
        request_key=key, graph_fingerprint=packet.graph_fingerprint,
        artifact_digest=None if artifact is None else wording_digest(artifact),
        diagnostics=tuple(diagnostics),
        items=tuple(ResolvedWordingItem(
            slot_id=target.slot_id,
            text=prepared[target.slot_id].text if target.slot_id in prepared else target.fallback_text,
            source_references=target.source_references,
            origin=artifact.origin if target.slot_id in prepared else "source_fallback",
        ) for target in packet.targets),
    )
