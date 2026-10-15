"""Explanation integration tests using a deterministic fake provider."""

import json
from pathlib import Path

import pytest

from app.core.explanations import (
    ExplanationInputError,
    ExplanationService,
    OutputRejected,
)
from app.core.llm_provider import ProviderFailure
from app.core.policy import SharedLinTSPolicy
from app.core.procedure_features import extract_structural_features
from app.core.procedure_graph import build_procedure_graph
from app.core.procedure_input import load_procedure_input
from app.core.user_context import InMemoryContextService
from app.models.explanations import (
    ExplanationDraft,
    ProviderCall,
    ProviderIdentity,
    ProviderReply,
)
from app.models.scaffolds import ContentSafety, Notice
from app.models.user_context import ContextUpdate, FamiliarityReport


FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "research"
    / "data"
    / "fixtures"
    / "linear"
)


class FakeProvider:
    def __init__(self, *, mutate=None, reject=False, failure=None):
        self.identity = ProviderIdentity(
            name="test",
            requested_model="fake-v1",
            sdk_version="test-v1",
        )
        self.mutate = mutate
        self.reject = reject
        self.failure = failure
        self.calls = []

    def complete(self, *, instructions, payload, response_model):
        self.calls.append((instructions, payload, response_model))
        if self.failure is not None:
            raise ProviderFailure(self.failure)

        packet = json.loads(payload)
        if response_model is ExplanationDraft:
            value = {
                "synthetic": packet["synthetic"],
                "items": [
                    {
                        "unit_id": unit["unit_id"],
                        "text": unit["source_content"],
                        "fact_ids": unit["fact_ids"],
                        "citations": [
                            {
                                "evidence_id": entry["evidence_id"],
                                "quote": entry["text"],
                            }
                            for entry in unit["evidence"]
                        ],
                    }
                    for unit in packet["units"]
                ],
            }
            if self.mutate is not None:
                value = self.mutate(value)
        else:
            value = {
                "items": [
                    {
                        "unit_id": unit["unit_id"],
                        "supported": not self.reject,
                        "preserves_meaning": not self.reject,
                        "contains_new_requirement": self.reject,
                        "reason": (
                            "Unsupported added requirement."
                            if self.reject
                            else "The proposed text preserves the supplied content."
                        ),
                    }
                    for unit in packet["source_packet"]["units"]
                ]
            }

        return ProviderReply(
            text=json.dumps(value),
            call=ProviderCall(
                response_id=f"fake-{len(self.calls)}",
                returned_model="fake-v1",
                input_tokens=10,
                output_tokens=10,
            ),
        )


@pytest.fixture
def setup():
    procedure = load_procedure_input(
        FIXTURES / "plan.json",
        FIXTURES / "enrichment.json",
    )
    graph = build_procedure_graph(procedure)
    features = extract_structural_features(graph)
    contexts = InMemoryContextService()
    session = contexts.create_session()
    policy = SharedLinTSPolicy(contexts)
    selected = policy.select_and_offer(
        session.session_id,
        graph,
        features,
        intended_action_ids=tuple(action.action_id for action in graph.actions),
    )
    return graph, features, contexts, session, policy, selected


def test_generated_result_preserves_all_source_records(setup):
    graph, _, _, _, _, selected = setup
    before = graph.model_dump_json()
    provider = FakeProvider()
    result = ExplanationService(provider).explain(graph, selected)

    assert result.origin == "generated"
    assert result.assurance == "automated_checks_only"
    assert result.source_status == "synthetic"
    assert result.source.graph == graph
    assert graph.model_dump_json() == before
    assert result.source.preservation == (
        selected.decision.evaluation.feasibility.preservation
    )
    assert len(result.explanations) == 2
    assert len(provider.calls) == 2
    assert result.exposure_id == selected.offer.exposure_id


def test_provider_packet_omits_session_identifiers_and_scores(setup):
    graph, _, _, session, _, selected = setup
    provider = FakeProvider()
    ExplanationService(provider).explain(graph, selected)

    payload = provider.calls[0][1]
    assert session.session_id not in payload
    assert selected.offer.exposure_id not in payload
    assert selected.decision.decision_id not in payload
    assert "navigation_capability" not in payload
    assert "matching_exposure_count" not in payload
    assert json.loads(payload)["writing_style"] == "plain"


@pytest.mark.parametrize(
    "problem",
    ["unknown_evidence", "invented_quote", "missing_unit", "changed_fact", "code"],
)
def test_invalid_generated_outputs_fall_back(problem, setup):
    graph, _, _, _, _, selected = setup

    def mutate(value):
        if problem == "unknown_evidence":
            value["items"][0]["citations"][0]["evidence_id"] = "evidence:unknown"
        elif problem == "invented_quote":
            value["items"][0]["citations"][0]["quote"] = (
                "This quotation never appeared in the supplied evidence."
            )
        elif problem == "missing_unit":
            value["items"].pop()
        elif problem == "changed_fact":
            value["items"][0]["fact_ids"] = ["svc:invented:fee"]
        else:
            value["items"][0]["text"] = "<script>alert('changed')</script>"
        return value

    provider = FakeProvider(mutate=mutate)
    result = ExplanationService(provider).explain(graph, selected)

    assert result.origin == "fallback"
    assert result.artifact is None
    assert result.assurance == "source_preserving_copy"
    assert len(provider.calls) == 1
    assert result.source.graph == graph

    originals = {block.content_id: block.text for block in graph.content}
    for item in result.explanations:
        assert item.text == originals[item.content_id]


def test_semantic_rejection_prevents_release_even_with_valid_citations(setup):
    graph, _, _, _, _, selected = setup

    def mutate(value):
        value["items"][0]["text"] += " You must also bring a passport."
        return value

    provider = FakeProvider(mutate=mutate, reject=True)
    result = ExplanationService(provider).explain(graph, selected)

    assert len(provider.calls) == 2
    assert result.origin == "fallback"
    assert "semantic_assessment_rejected" in result.diagnostics
    assert all("passport" not in item.text for item in result.explanations)


def test_provider_failure_fallback_is_deterministic_and_not_cached(setup):
    graph, _, _, _, _, selected = setup
    provider = FakeProvider(failure="provider_unavailable")
    service = ExplanationService(provider)

    first = service.explain(graph, selected)
    second = service.explain(graph, selected)

    assert first == second
    assert first.origin == "fallback"
    assert first.diagnostics == ("provider_unavailable",)
    assert len(provider.calls) == 2


def test_cache_hit_rebinds_to_current_offer_without_new_requests(setup):
    graph, features, contexts, _, policy, selected = setup
    provider = FakeProvider()
    service = ExplanationService(provider)
    first = service.explain(graph, selected)

    other = contexts.create_session()
    other_offer = policy.select_and_offer(
        other.session_id,
        graph,
        features,
        intended_action_ids=selected.offer.intended_action_ids,
    )
    second = service.explain(graph, other_offer)

    assert first.request_key == second.request_key
    assert second.cache_hit is True
    assert second.exposure_id == other_offer.offer.exposure_id
    assert second.exposure_id != first.exposure_id
    assert len(provider.calls) == 2


def test_changed_writing_style_creates_a_different_cache_entry(setup):
    graph, features, contexts, session, policy, selected = setup
    provider = FakeProvider()
    service = ExplanationService(provider)
    first = service.explain(graph, selected)

    contexts.update_context(
        session.session_id,
        ContextUpdate(
            familiarity=FamiliarityReport(
                service_id=graph.requested_service_id,
                score=5,
            ),
            navigation_capability=5,
        ),
        expected_revision=0,
    )
    changed = policy.select_and_offer(
        session.session_id,
        graph,
        features,
        intended_action_ids=selected.offer.intended_action_ids,
    )
    second = service.explain(graph, changed)

    assert first.request_key != second.request_key
    assert second.cache_hit is False
    assert len(provider.calls) == 4


def test_graph_mismatch_is_an_input_error_without_api_calls(setup):
    graph, _, _, _, _, selected = setup
    provider = FakeProvider()
    changed = graph.model_copy(update={"plan_id": "different-plan"})

    with pytest.raises(ExplanationInputError):
        ExplanationService(provider).explain(changed, selected)
    assert provider.calls == []


def test_external_warnings_are_preserved_and_safety_mismatch_is_rejected(setup):
    graph, features, contexts, session, policy, _ = setup
    safety = ContentSafety(
        warnings=(
            Notice(
                notice_id="research:warning",
                text="This fictional procedure is for demonstration only.",
            ),
        )
    )
    selected = policy.select_and_offer(
        session.session_id,
        graph,
        features,
        intended_action_ids=tuple(action.action_id for action in graph.actions),
        safety=safety,
    )
    service = ExplanationService(FakeProvider())

    with pytest.raises(ExplanationInputError):
        service.explain(graph, selected)

    result = service.explain(graph, selected, safety=safety)
    assert safety.warnings[0] in result.source.notices


def test_export_import_and_exact_artifact_review_work_offline(setup):
    graph, _, _, _, _, selected = setup
    service = ExplanationService(FakeProvider())
    first = service.explain(graph, selected)

    reviewed = service.mark_reviewed(
        first.request_key,
        reviewer_reference="test-review",
    )
    assert reviewed.review is not None
    exported = service.export_artifact(first.request_key)

    offline_provider = FakeProvider(failure="provider_disabled")
    offline = ExplanationService(offline_provider)
    offline.load_artifact(exported)
    result = offline.explain(graph, selected)

    assert result.cache_hit is True
    assert result.assurance == "human_reviewed_against_supplied_sources"
    assert offline_provider.calls == []

    altered = json.loads(exported)
    altered["draft"]["items"][0]["text"] += " Altered after review."
    with pytest.raises(OutputRejected, match="review_digest"):
        offline.load_artifact(json.dumps(altered))


def test_schema_errors_and_synthetic_misclassification_are_rejected(setup):
    graph, _, _, _, _, selected = setup

    def mutate(value):
        value["synthetic"] = False
        return value

    result = ExplanationService(FakeProvider(mutate=mutate)).explain(
        graph, selected
    )
    assert result.origin == "fallback"
    assert "synthetic_classification_changed" in result.diagnostics

    def extra_field(value):
        value["new_workflow_edges"] = []
        return value

    result = ExplanationService(FakeProvider(mutate=extra_field)).explain(
        graph, selected
    )
    assert result.origin == "fallback"
    assert "invalid_response_schema" in result.diagnostics