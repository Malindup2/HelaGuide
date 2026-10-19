"""Source linkage and offline preparation tests; no real LLM calls."""

import json

import pytest
from pydantic import ValidationError

from app.core.demo_procedures import load_demo_procedures, FIXTURES_ROOT
from app.core.explanation_store import ArtifactStoreError
from app.core.explanations import OutputRejected
from app.core.llm_provider import ProviderFailure
from app.core.prepared_wording import (
    prepare_wording_packet, ref, source_records, validate_wording_artifact,
    validate_wording_draft, wording_key,
)
from app.core.procedure_features import extract_structural_features
from app.core.scaffolds import enumerate_scaffolds, filter_scaffolds
from app.core.wording_service import (
    PreparedWordingStore, generate_wording, human_template, make_human_artifact,
    preparation_batches, resolve_wording,
)
from app.models.explanations import ProviderCall, ProviderIdentity, ProviderReply
from app.models.prepared_wording import WordingAssessment, WordingDraft
from app.wording_artifacts import main


@pytest.fixture
def graphs():
    return load_demo_procedures()[0]


def filled_draft(packet):
    """Mechanical test fixture, not validated citizen wording or real review."""
    template = human_template(packet, author_reference="test-author")
    for item, target in zip(template["draft"]["items"], packet.targets):
        # Explicitly synthetic test text, kept short for every label field.
        item["text"] = "Fictional demo guidance."
    return WordingDraft.model_validate_json(json.dumps(template["draft"]))


class FakeWordingProvider:
    identity = ProviderIdentity(name="test", requested_model="fake-wording", sdk_version="test")

    def __init__(self, *, reject=False, mutate=None, failure_after=None):
        self.calls = []
        self.reject = reject
        self.mutate = mutate
        self.failure_after = failure_after

    def complete(self, *, instructions, payload, response_model):
        self.calls.append((instructions, json.loads(payload), response_model))
        if self.failure_after is not None and len(self.calls) > self.failure_after:
            raise ProviderFailure("fake_provider_failure")
        supplied = json.loads(payload)
        if response_model is WordingDraft:
            sources = {record["reference"]["reference_id"]: record["record"]
                       for record in supplied["sources"] if record["reference"]["kind"] == "evidence"}
            value = {"synthetic": supplied["synthetic"], "items": [
                {"slot_id": target["slot_id"], "text": "Fictional demo guidance.",
                 "source_references": target["source_references"],
                 "citations": [{"evidence_id": key, "quote": sources[key]["text"][:4000]}
                               for key in target["evidence_ids"]]}
                for target in supplied["targets"]
            ]}
            if self.mutate:
                value = self.mutate(value)
        else:
            value = {"items": [
                {"slot_id": item["slot_id"], "supported": not self.reject,
                 "preserves_meaning": not self.reject, "contains_new_requirement": self.reject,
                 "reason": "Fake assessment for mechanical tests only."}
                for item in supplied["proposed_wording"]["items"]
            ]}
        return ProviderReply(text=json.dumps(value), call=ProviderCall(
            response_id=f"fake-{len(self.calls)}", returned_model="fake-wording",
            input_tokens=10, output_tokens=10,
        ))


def test_manifest_has_exact_source_subjects_for_all_scenarios(graphs):
    for graph in graphs:
        packet = prepare_wording_packet(graph)
        records = source_records(graph)
        assert len({target.slot_id for target in packet.targets}) == len(packet.targets)
        action_slots = [target for target in packet.targets if target.subject.kind == "action"]
        assert len(action_slots) == 4 * len(graph.actions)
        for target in packet.targets:
            assert target.subject in records
            assert set(target.source_references) <= records.keys()
        prerequisites = [target for target in packet.targets if target.kind == "prerequisite_explanation"]
        assert {target.subject for target in prerequisites} == {
            ref("action_prerequisite", edge.edge_id) for edge in graph.action_prerequisites
        } | {ref("stage_dependency", edge.edge_id) for edge in graph.stage_dependencies}
        assert len([target for target in packet.targets if target.subject.kind == "branch_option"]) == sum(
            len(group.options) for group in graph.branch_groups
        )
        assert len([target for target in packet.targets if target.subject.kind == "parallel_group"]) == len(graph.parallel_groups)


def test_condition_and_branch_links_survive_in_action_targets(graphs):
    graph = graphs[1]
    packet = prepare_wording_packet(graph)
    for action in graph.actions:
        targets = [target for target in packet.targets if target.subject == ref("action", action.action_id)]
        for target in targets:
            for condition_id in action.applicability.condition_ids:
                assert ref("condition", condition_id) in target.source_references
            if action.applicability.branch_group_id:
                assert ref("branch_group", action.applicability.branch_group_id) in target.source_references
                assert ref("branch_option", action.applicability.branch_option_id) in target.source_references


def test_one_wording_key_is_independent_of_all_64_configurations(graphs):
    graph = graphs[1]
    packet = prepare_wording_packet(graph)
    key = wording_key(packet)
    assert len(enumerate_scaffolds()) == 64
    for configuration in enumerate_scaffolds():
        assert configuration.configuration_id not in packet.model_dump_json()
        assert wording_key(prepare_wording_packet(graph)) == key
    assert wording_key(prepare_wording_packet(graph, writing_style="concise")) != key
    changed = graph.model_copy(update={"disclaimer": graph.disclaimer + " Source revision."})
    assert wording_key(prepare_wording_packet(changed)) != key


@pytest.mark.parametrize("change", ["unknown_slot", "duplicate", "source", "quote", "number", "html", "length", "synthetic", "order"])
def test_invalid_drafts_are_rejected(graphs, change):
    packet = prepare_wording_packet(graphs[0])
    data = filled_draft(packet).model_dump(mode="json")
    if change == "unknown_slot":
        data["items"][0]["slot_id"] = "invented"
    elif change == "duplicate":
        data["items"].append(data["items"][0])
    elif change == "source":
        data["items"][0]["source_references"] = []
    elif change == "quote":
        data["items"][0]["citations"][0]["quote"] = "This quotation is invented."
    elif change == "number":
        data["items"][0]["text"] = "Pay 987654321."
    elif change == "html":
        data["items"][0]["text"] = "<script>run()</script>"
    elif change == "length":
        data["items"][0]["text"] = "a" * 121
    elif change == "synthetic":
        data["synthetic"] = False
    else:
        data["items"] = list(reversed(data["items"]))
    with pytest.raises(OutputRejected):
        validate_wording_draft(packet, WordingDraft.model_validate_json(json.dumps(data)))


def test_empty_editorial_template_cannot_be_imported_as_wording(graphs):
    packet = prepare_wording_packet(graphs[0])
    with pytest.raises(ValidationError):
        WordingDraft.model_validate_json(json.dumps(human_template(packet, author_reference="test")["draft"]))


def test_human_partial_bundle_requires_explicit_opt_in_and_falls_back_per_slot(graphs, tmp_path):
    graph = graphs[0]
    packet = prepare_wording_packet(graph)
    draft = filled_draft(packet)
    partial = draft.model_copy(update={"items": draft.items[:1]})
    with pytest.raises(OutputRejected):
        make_human_artifact(packet, partial, author_reference="test-author")
    artifact = make_human_artifact(packet, partial, author_reference="test-author", allow_partial=True)
    store = PreparedWordingStore(tmp_path)
    store.save(artifact)
    assert all(item.origin == "source_fallback" for item in resolve_wording(graph, store).items)
    store.review(artifact.request_key, reviewer_reference="test-review")
    result = resolve_wording(graph, PreparedWordingStore(tmp_path))
    assert result.items[0].origin == "human_prepared"
    assert all(item.origin == "source_fallback" for item in result.items[1:])
    assert "wording_partial_source_fallback" in result.diagnostics
    assert store.read(artifact.request_key).provider is None


def test_reviewed_artifacts_cannot_be_silently_overwritten(graphs, tmp_path):
    packet = prepare_wording_packet(graphs[0])
    artifact = make_human_artifact(packet, filled_draft(packet), author_reference="test-author")
    store = PreparedWordingStore(tmp_path)
    store.save(artifact)
    changed = artifact.model_copy(update={"author_reference": "another-test-author"})
    with pytest.raises(ArtifactStoreError):
        store.save(changed)
    store.save(changed, replace_pending=True)
    store.review(changed.request_key, reviewer_reference="test-review")
    with pytest.raises(ArtifactStoreError):
        store.save(artifact, replace_pending=True)


@pytest.mark.parametrize("change", ["text", "manifest", "key", "version", "review", "provenance", "missing_graph_reference"])
def test_tampering_does_not_survive_read_or_resolution(graphs, tmp_path, change):
    graph = graphs[0]
    packet = prepare_wording_packet(graph)
    artifact = make_human_artifact(packet, filled_draft(packet), author_reference="test-author")
    store = PreparedWordingStore(tmp_path)
    store.save(artifact)
    reviewed = store.review(artifact.request_key, reviewer_reference="test-review")
    data = reviewed.model_dump(mode="json")
    if change == "text":
        data["draft"]["items"][0]["text"] = "Changed wording."
    elif change == "manifest":
        data["source"]["targets"][0]["fallback_text"] = "Altered source."
    elif change == "key":
        data["request_key"] = "a" * 64
    elif change == "version":
        data["recipe_version"] = "old"
    elif change == "review":
        data["review"]["artifact_digest"] = "invalid"
    elif change == "provenance":
        data["origin"] = "provider_generated"
    else:
        data["source"]["graph"]["actions"] = []
    path = tmp_path / f"{artifact.request_key}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    result = resolve_wording(graph, store)
    assert result.diagnostics
    assert result.artifact_digest is None
    assert all(item.origin == "source_fallback" for item in result.items)


def test_source_style_and_recipe_invalidate_reuse(graphs, tmp_path, monkeypatch):
    graph = graphs[0]
    packet = prepare_wording_packet(graph)
    store = PreparedWordingStore(tmp_path)
    artifact = make_human_artifact(packet, filled_draft(packet), author_reference="test-author")
    store.save(artifact)
    store.review(artifact.request_key, reviewer_reference="test-review")
    assert resolve_wording(graph, store).artifact_digest is not None
    assert resolve_wording(graph, store, writing_style="concise").artifact_digest is None
    changed = graph.model_copy(update={"disclaimer": graph.disclaimer + " Source changed."})
    assert resolve_wording(changed, store).artifact_digest is None
    monkeypatch.setattr("app.core.prepared_wording.RECIPE_VERSION", "new-test-recipe")
    assert resolve_wording(graph, store).artifact_digest is None


def test_no_graph_feature_feasibility_or_policy_dimension_changes(graphs, tmp_path):
    from app.core.policy import FEATURE_DIMENSION
    for graph in graphs:
        before = graph.model_dump_json()
        features = extract_structural_features(graph)
        feasible = filter_scaffolds(graph, features)
        resolve_wording(graph, PreparedWordingStore(tmp_path))
        assert graph.model_dump_json() == before
        assert extract_structural_features(graph) == features
        assert filter_scaffolds(graph, features) == feasible
    assert FEATURE_DIMENSION == 656


def test_provider_preparation_batches_validates_and_preserves_actual_call_records(graphs):
    packet = prepare_wording_packet(graphs[1])
    provider = FakeWordingProvider()
    artifact = generate_wording(packet, provider)
    batches = preparation_batches(packet)
    assert len(provider.calls) == len(batches) * 2
    assert artifact.review is None
    assert artifact.origin == "provider_generated"
    assert artifact.provider.name == "test"
    assert len(artifact.draft.items) == len(packet.targets)
    assert len(artifact.generation_calls) == len(batches)
    assert len(artifact.assessment_calls) == len(batches)
    validate_wording_artifact(artifact)
    for _, payload, _ in provider.calls:
        encoded = json.dumps(payload)
        for private_field in ("session_id", "exposure_id", "configuration_id", "navigation_capability"):
            assert private_field not in encoded


def test_budget_and_oversized_targets_fail_before_paid_calls(graphs, monkeypatch):
    packet = prepare_wording_packet(graphs[0])
    provider = FakeWordingProvider()
    with pytest.raises(OutputRejected, match="budget"):
        generate_wording(packet, provider, max_batches=0)
    assert provider.calls == []
    monkeypatch.setattr("app.core.wording_service.MAX_SOURCE_BYTES", 1)
    with pytest.raises(OutputRejected, match="too_large"):
        generate_wording(packet, provider)
    assert provider.calls == []


def test_semantic_and_mid_batch_failures_do_not_approve_or_persist(graphs, tmp_path):
    packet = prepare_wording_packet(graphs[1])
    store = PreparedWordingStore(tmp_path)
    with pytest.raises(OutputRejected, match="assessment"):
        generate_wording(packet, FakeWordingProvider(reject=True))
    with pytest.raises(ProviderFailure):
        generate_wording(packet, FakeWordingProvider(failure_after=2))
    assert store.files.keys() == ()


def test_source_free_labels_cannot_invent_citations(graphs):
    packet = prepare_wording_packet(graphs[0])
    draft = filled_draft(packet)
    index = next(i for i, target in enumerate(packet.targets) if not target.evidence_ids)
    data = draft.model_dump(mode="json")
    data["items"][index]["citations"] = [{"evidence_id": "invented", "quote": "Invented evidence."}]
    with pytest.raises(OutputRejected, match="evidence"):
        validate_wording_draft(packet, WordingDraft.model_validate_json(json.dumps(data)))


def test_cli_human_workflow_and_current_source_binding(graphs, tmp_path, capsys):
    store_dir = tmp_path / "store"
    editorial = tmp_path / "editorial.json"
    prefix = ["--directory", str(store_dir)]
    assert main(prefix + ["plan", "--scenario", "linear"]) == 0
    assert "live_calls_made=0" in capsys.readouterr().out
    assert main(prefix + ["template", "--scenario", "linear", "--author", "test-author", "--output", str(editorial)]) == 0
    assert main(prefix + ["import-human", "--scenario", "linear", "--input", str(editorial)]) == 1
    value = json.loads(editorial.read_text(encoding="utf-8"))
    packet = prepare_wording_packet(graphs[0])
    value["draft"] = filled_draft(packet).model_dump(mode="json")
    editorial.write_text(json.dumps(value), encoding="utf-8")
    assert main(prefix + ["validate-human", "--scenario", "linear", "--input", str(editorial)]) == 0
    assert not store_dir.exists()
    assert main(prefix + ["import-human", "--scenario", "conditional", "--input", str(editorial)]) == 1
    assert main(prefix + ["import-human", "--scenario", "linear", "--input", str(editorial)]) == 0
    key = wording_key(packet)
    assert main(prefix + ["list"]) == 0
    assert main(prefix + ["show", key]) == 0
    with pytest.raises(SystemExit):
        main(prefix + ["review", key, "--reviewer", "test-review"])
    assert main(prefix + ["review", key, "--reviewer", "test-review", "--confirm-source-check"]) == 0
    assert main(prefix + ["resolve", "--scenario", "linear"]) == 0
    assert '"origin": "human_prepared"' in capsys.readouterr().out
    assert main(prefix + ["template", "--scenario", "linear", "--author", "test-author", "--output", str(editorial)]) == 1


def test_new_c2_shaped_input_uses_same_pipeline(tmp_path):
    plan = json.loads((FIXTURES_ROOT / "linear" / "plan.json").read_text(encoding="utf-8"))
    enrichment = json.loads((FIXTURES_ROOT / "linear" / "enrichment.json").read_text(encoding="utf-8"))
    plan["plan_id"] = "new-procedure-test"
    enrichment["plan_id"] = "new-procedure-test"
    plan_file, enrichment_file = tmp_path / "plan.json", tmp_path / "enrichment.json"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")
    enrichment_file.write_text(json.dumps(enrichment), encoding="utf-8")
    assert main(["plan", "--plan", str(plan_file), "--enrichment", str(enrichment_file)]) == 0


def test_live_cli_requires_both_gates_and_explicit_confirmation(tmp_path, monkeypatch):
    prefix = ["--directory", str(tmp_path)]
    with pytest.raises(SystemExit):
        main(prefix + ["generate", "--scenario", "linear"])
    monkeypatch.setenv("C4_DEV_LLM_ENABLED", "false")
    monkeypatch.setenv("C4_LLM_ENABLED", "false")
    assert main(prefix + ["generate", "--scenario", "linear", "--confirm-live-request"]) == 1
    assert not list(tmp_path.iterdir())


def test_corrupt_store_and_removed_reviewed_file_fall_back(graphs, tmp_path):
    graph = graphs[0]
    packet = prepare_wording_packet(graph)
    store = PreparedWordingStore(tmp_path)
    artifact = make_human_artifact(packet, filled_draft(packet), author_reference="test-author")
    store.save(artifact)
    store.review(artifact.request_key, reviewer_reference="test-review")
    assert resolve_wording(graph, store).artifact_digest
    path = tmp_path / f"{artifact.request_key}.json"
    path.write_text("{bad-json", encoding="utf-8")
    assert resolve_wording(graph, store).diagnostics == ("artifact_invalid_schema",)
    path.unlink()
    assert resolve_wording(graph, store).diagnostics == ("wording_not_prepared",)
