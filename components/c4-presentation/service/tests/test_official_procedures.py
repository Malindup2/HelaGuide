"""Source snapshot structure, safe rendering and catalogue upgrade recovery."""
import json
from shutil import copytree

import pytest
from fastapi.testclient import TestClient

from app.procedures.demo_procedures import load_demo_procedures
from app.procedures.official_procedures import OFFICIAL_ROOT, load_official_procedures, load_registered_procedures
from app.procedures.procedure_features import extract_structural_features
from app.procedures.procedure_input import ProcedureInputError
from app.procedures.scaffolds import filter_scaffolds, graph_fingerprint
from app.dev_main import create_app
from tests.test_explanations import FakeProvider


@pytest.mark.parametrize("index, actions, branches, conditions, dependencies, selection", [
    (0, 2, 0, 0, 1, None), (1, 3, 1, 2, 1, "XOR"), (2, 5, 0, 0, 4, None),
])
def test_bounded_source_structure_and_safe_candidates(index, actions, branches, conditions, dependencies, selection):
    graphs, safety = load_official_procedures()
    graph = graphs[index]
    features = extract_structural_features(graph)
    assert not graph.synthetic
    assert features.step_count.exact_value == actions
    assert features.branch_count.exact_value == branches
    assert features.condition_count.exact_value == conditions
    assert features.dependency_count.exact_value == dependencies
    assert features.parallel_group_count.exact_value is None
    assert not graph.parallel_groups
    assert all(e.kind == "source_passage" and e.retrieved_at for e in graph.evidence)
    assert all(e.source_url.startswith("https://") for e in graph.evidence)
    assert {g.selection for g in graph.branch_groups} == ({selection} if selection else set())
    scope = next(b for b in graph.content if b.content_id == "content:scope")
    assert "not independently validated" in scope.text
    assert "Scope:" in scope.text
    assert all(scope.content_id in a.required_content_ids for a in graph.actions)
    assert all(a.required_content_ids[0] != scope.content_id for a in graph.actions)
    assert all(f.value > 0 for f in graph.facts if f.kind == "fee")
    result = filter_scaffolds(graph, features, safety=safety[graph_fingerprint(graph)])
    candidates = result.feasible_candidates()
    assert candidates
    assert not result.preservation.collapsible_content_ids
    assert not any(c.progressive_disclosure or c.presentation_mode == "GUIDED" or c.relationship_visual == "PARALLEL_MAP" for c in candidates)
    assert {c.relationship_visual for c in candidates} == ({"NONE", "DEPENDENCY_MAP", "BRANCH_MAP"} if selection else {"NONE", "DEPENDENCY_MAP"})


def test_mixed_catalogue_keeps_existing_fingerprints_and_safety():
    old, old_safety = load_demo_procedures()
    mixed, mixed_safety = load_registered_procedures()
    assert mixed[:3] == old
    assert len(mixed) == 9
    assert len({g.plan_id for g in mixed}) == 9
    assert all(mixed_safety[k] == v for k, v in old_safety.items())


def test_invalid_local_snapshot_fails_instead_of_disappearing(tmp_path):
    root = tmp_path / "official"
    copytree(OFFICIAL_ROOT, root)
    path = root / "nic_amendment" / "enrichment.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["evidence"][0]["retrieved_at"] = None
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ProcedureInputError, match="needs retrieved_at"):
        load_official_procedures(root)


@pytest.mark.parametrize("plan_id, visual", [
    ("official-birth_copy-v3", "DEPENDENCY_MAP"),
    ("official-nic_amendment-v3", "BRANCH_MAP"),
    ("official-company_pack-v3", "DEPENDENCY_MAP"),
])
def test_source_fallback_and_supported_diagram_keep_protected_scope(plan_id, visual):
    app = create_app(provider=FakeProvider(failure="offline_test"), include_official_examples=True)
    with TestClient(app) as client:
        procedure = next(p for p in client.get("/dev/v1/procedures").json() if p["plan_id"] == plan_id)
        session = client.post("/dev/v1/sessions").json()
        base = f"/dev/v1/sessions/{session['session_id']}"
        changed = client.patch(base + "/context", json={"expected_revision": session["revision"],
            "update": {"locks": {"presentation_mode": "OVERVIEW", "relationship_visual": visual}}})
        assert changed.status_code == 200, changed.text
        selected = client.post(base + "/presentations", json={"procedure_id": procedure["procedure_id"], "expected_revision": changed.json()["revision"]})
        assert selected.status_code == 201, selected.text
        spec = selected.json()["spec"]
        assert spec["diagram"]["kind"] == visual
        assert spec["explanation"]["origin"] == "fallback"
        graph = spec["explanation"]["source"]["graph"]
        assert not graph["synthetic"]
        cards = {(c["source"]["kind"], c["source"]["identifier"]): c for c in spec["cards"]}
        for content in graph["content"]:
            card = cards[("content", content["content_id"])]
            assert card["lines"] == [content["text"]]
            assert not card["collapsed"]
        assert app.state.runtime.policy.posterior_revision == 0


def test_catalogue_upgrade_preserves_saved_policy_and_presentation(tmp_path):
    path = tmp_path / "runtime.sqlite3"
    with TestClient(create_app(provider=FakeProvider(failure="offline_test"), database_path=path)) as client:
        procedure = client.get("/dev/v1/procedures").json()[0]
        session = client.post("/dev/v1/sessions").json()
        base = f"/dev/v1/sessions/{session['session_id']}"
        selected = client.post(base + "/presentations", json={"procedure_id": procedure["procedure_id"], "expected_revision": session["revision"]})
        assert selected.status_code == 201, selected.text
        original_spec = selected.json()["spec"]
        before = client.get("/dev/v1/policy").json()
    app = create_app(provider=FakeProvider(failure="offline_test"), database_path=path, include_official_examples=True)
    with TestClient(app) as client:
        assert len(client.get("/dev/v1/procedures").json()) == 9
        assert app.state.runtime.presentations[original_spec["exposure_id"]].model_dump(mode="json") == original_spec
        after = client.get("/dev/v1/policy").json()
        for field in ("policy_run_id", "posterior_fingerprint", "posterior_revision", "accepted_feedback_count", "prior_digest"):
            assert after[field] == before[field]
