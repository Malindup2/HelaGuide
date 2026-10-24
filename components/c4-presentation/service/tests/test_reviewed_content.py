"""Durable content tests. Fake provider results are not real LLM evidence."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.preparation.content_cli import main
from app.preparation.explanation_store import (
    ArtifactStoreError, ExplanationArtifactStore, parse_stored,
)
from app.preparation.explanations import ExplanationService, OutputRejected
from app.preparation.llm_provider import OpenAIExplanationProvider
from app.procedures.procedure_graph import build_procedure_graph
from app.procedures.procedure_input import load_procedure_input
from app.dev_main import create_app
from tests.test_dev_api import select, start
from tests.test_explanations import FIXTURES, FakeProvider, setup


def test_reviewed_package_survives_new_service_and_new_exposure(setup, tmp_path):
    graph, features, _, session, policy, selected = setup
    store = ExplanationArtifactStore(tmp_path)
    service = ExplanationService(FakeProvider(), artifact_store=store)
    first = service.explain(graph, selected)
    service.mark_reviewed(first.request_key, reviewer_reference="unit-test-review")

    offline_provider = FakeProvider(failure="must_not_be_called")
    restarted = ExplanationService(
        offline_provider, artifact_store=ExplanationArtifactStore(tmp_path),
        reviewed_only=True, generation_enabled=False,
    )
    second_offer = policy.select_and_offer(
        session.session_id, graph, features,
        intended_action_ids=tuple(item.action_id for item in graph.actions),
    )
    second = restarted.explain(graph, second_offer)
    assert second.origin == "generated"
    assert second.cache_hit
    assert second.assurance == "human_reviewed_against_supplied_sources"
    assert second.exposure_id == second_offer.offer.exposure_id
    assert second.exposure_id != first.exposure_id
    assert second.source.graph == graph
    assert offline_provider.calls == []


def test_live_preparation_is_saved_pending_and_not_displayed_as_reviewed(setup, tmp_path):
    graph, _, _, _, _, selected = setup
    provider = FakeProvider()
    store = ExplanationArtifactStore(tmp_path)
    service = ExplanationService(provider, artifact_store=store, reviewed_only=True)
    result = service.explain(graph, selected)
    assert len(provider.calls) == 2
    assert result.origin == "fallback"
    assert result.artifact is None
    assert result.diagnostics == ("human_review_required",)
    assert store.read(result.request_key).artifact.review is None
    # Pending content neither triggers another paid call nor appears reviewed.
    service.explain(graph, selected)
    assert len(provider.calls) == 2
    service.mark_reviewed(result.request_key, reviewer_reference="unit-test-review")
    assert service.explain(graph, selected).origin == "generated"


def test_offline_missing_and_unreviewed_never_call_provider(setup, tmp_path):
    graph, _, _, _, _, selected = setup
    store = ExplanationArtifactStore(tmp_path)
    provider = FakeProvider()
    offline = ExplanationService(
        provider, artifact_store=store, reviewed_only=True, generation_enabled=False,
    )
    missing = offline.explain(graph, selected)
    assert missing.diagnostics == ("provider_disabled",)
    assert provider.calls == []
    ExplanationService(FakeProvider(), artifact_store=store).explain(graph, selected)
    pending = offline.explain(graph, selected)
    assert pending.diagnostics == ("human_review_required",)
    assert pending.origin == "fallback"
    assert provider.calls == []


@pytest.mark.parametrize("change", ["text", "review", "packet", "prompt", "validation", "assessment"])
def test_tampered_or_stale_packages_fall_back(setup, tmp_path, change):
    graph, _, _, _, _, selected = setup
    store = ExplanationArtifactStore(tmp_path)
    service = ExplanationService(FakeProvider(), artifact_store=store)
    first = service.explain(graph, selected)
    service.mark_reviewed(first.request_key, reviewer_reference="unit-test-review")
    path = tmp_path / (first.request_key + ".json")
    value = json.loads(path.read_text(encoding="utf-8"))
    artifact = value["artifact"]
    if change == "text":
        artifact["draft"]["items"][0]["text"] += " Changed."
    elif change == "review":
        artifact["review"]["artifact_digest"] = "bad"
    elif change == "packet":
        value["source_packet"]["writing_style"] = "concise"
    elif change == "assessment":
        artifact["assessment"]["items"][0]["supported"] = False
    else:
        artifact[change + "_version"] = "old-version"
    path.write_text(json.dumps(value), encoding="utf-8")
    provider = FakeProvider()
    result = ExplanationService(
        provider, artifact_store=store, reviewed_only=True, generation_enabled=False,
    ).explain(graph, selected)
    assert result.origin == "fallback"
    assert result.diagnostics
    assert result.source.graph == graph
    assert provider.calls == []


def test_deleted_artifact_revokes_memory_approval(setup, tmp_path):
    graph, _, _, _, _, selected = setup
    service = ExplanationService(
        FakeProvider(), artifact_store=ExplanationArtifactStore(tmp_path),
    )
    first = service.explain(graph, selected)
    service.mark_reviewed(first.request_key, reviewer_reference="unit-test-review")
    service.reviewed_only = True
    service.generation_enabled = False
    assert service.explain(graph, selected).origin == "generated"
    (tmp_path / (first.request_key + ".json")).unlink()
    assert service.explain(graph, selected).origin == "fallback"


def test_source_provider_and_style_changes_do_not_reuse_approval(setup, tmp_path):
    graph, _, _, _, _, selected = setup
    store = ExplanationArtifactStore(tmp_path)
    provider = FakeProvider()
    service = ExplanationService(provider, artifact_store=store)
    first = service.explain_standard(graph)
    service.mark_reviewed(first.request_key, reviewer_reference="unit-test-review")
    offline = ExplanationService(
        provider, artifact_store=store, reviewed_only=True, generation_enabled=False,
    )
    assert offline.explain_standard(graph).origin == "generated"
    assert offline.explain_standard(graph, writing_style="concise").origin == "fallback"
    changed = graph.model_copy(update={"disclaimer": graph.disclaimer + " Revised source."})
    assert offline.explain_standard(changed).origin == "fallback"
    provider.identity = provider.identity.model_copy(update={"requested_model": "new-model"})
    assert offline.explain_standard(graph).origin == "fallback"


def test_corrupt_json_and_bad_keys_are_rejected(setup, tmp_path):
    store = ExplanationArtifactStore(tmp_path)
    with pytest.raises(ArtifactStoreError, match="invalid_key"):
        store.read("../outside")
    with pytest.raises(ArtifactStoreError, match="duplicate"):
        parse_stored('{"schema_version":"a","schema_version":"b"}')
    with pytest.raises(ArtifactStoreError, match="non_finite"):
        parse_stored('{"x":NaN}')
    graph, _, _, _, _, selected = setup
    service = ExplanationService(FakeProvider(), artifact_store=store)
    first = service.explain(graph, selected)
    (tmp_path / (first.request_key + ".json")).write_text("{broken", encoding="utf-8")
    result = service.explain(graph, selected)
    assert result.origin == "fallback"
    assert result.diagnostics == ("artifact_invalid_schema",)


def test_store_write_failure_produces_explicit_fallback(setup, tmp_path, monkeypatch):
    graph, _, _, _, _, selected = setup
    store = ExplanationArtifactStore(tmp_path)
    def fail(stored):
        raise ArtifactStoreError("artifact_write_failed")
    monkeypatch.setattr(store, "write", fail)
    result = ExplanationService(FakeProvider(), artifact_store=store).explain(graph, selected)
    assert result.origin == "fallback"
    assert result.diagnostics == ("artifact_write_failed",)


def test_local_review_tool_preserves_test_provider_provenance(setup, tmp_path, capsys):
    graph, _, _, _, _, selected = setup
    service = ExplanationService(FakeProvider(), artifact_store=ExplanationArtifactStore(tmp_path))
    result = service.explain(graph, selected)
    prefix = ["--directory", str(tmp_path)]
    assert main(prefix + ["list"]) == 0
    assert "pending_review" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(prefix + ["review", result.request_key, "--reviewer", "unit-test-review"])
    assert main(prefix + ["review", result.request_key, "--reviewer", "unit-test-review",
                          "--confirm-source-check"]) == 0
    assert "provider=test" in capsys.readouterr().out
    assert main(prefix + ["show", result.request_key]) == 0
    assert '"source_packet"' in capsys.readouterr().out
    assert main(prefix + ["list"]) == 0
    assert "pending_review" not in capsys.readouterr().out


def test_real_adapter_off_gate_keeps_configured_identity(monkeypatch):
    monkeypatch.setenv("C4_LLM_MODEL", "configured-model-test")
    monkeypatch.setenv("C4_LLM_ENABLED", "true")
    provider = OpenAIExplanationProvider.from_environment(allow_live=False)
    assert provider.identity.requested_model == "configured-model-test"
    from app.preparation.llm_provider import ProviderFailure
    with pytest.raises(ProviderFailure, match="provider_disabled"):
        provider._get_client()


def test_application_restart_reuses_reviewed_content_without_policy_migration(tmp_path):
    content = tmp_path / "content"
    database = tmp_path / "runtime.sqlite3"
    graph = build_procedure_graph(load_procedure_input(
        FIXTURES / "plan.json", FIXTURES / "enrichment.json",
    ))
    first_app = create_app(
        provider=FakeProvider(), graphs=(graph,), database_path=database,
        content_directory=content, reviewed_content_only=True,
    )
    with TestClient(first_app) as client:
        procedure_id, session = start(client)
        spec = select(client, procedure_id, session).json()["spec"]
        assert spec["explanation"]["origin"] == "fallback"
        key = spec["explanation"]["request_key"]
        first_app.state.runtime.explanations.mark_reviewed(key, reviewer_reference="unit-test-review")
        revision = first_app.state.runtime.policy.posterior_revision
    provider = FakeProvider(failure="must_not_be_called")
    restarted = create_app(
        provider=provider, graphs=(graph,), database_path=database,
        content_directory=content, reviewed_content_only=True,
    )
    with TestClient(restarted) as client:
        procedure_id, new_session = start(client)
        new_spec = select(client, procedure_id, new_session).json()["spec"]
        assert new_spec["explanation"]["origin"] == "generated"
        assert new_spec["explanation"]["cache_hit"]
        assert new_spec["exposure_id"] != spec["exposure_id"]
        assert restarted.state.runtime.policy.posterior_revision == revision
        assert provider.calls == []
        assert client.get("/health").json()["content"]["reviewed_only"]
