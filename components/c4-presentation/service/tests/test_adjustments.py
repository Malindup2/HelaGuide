"""Manual views preserve source coverage and never become sampled-action rewards."""
import json
from uuid import uuid4
from fastapi.testclient import TestClient
from tests.test_pipeline_trace import backend, offer, config, feedback_body
from tests.test_guidance_routing import profile, session_base
from app.dev_main import create_app
from tests.test_explanations import FakeProvider

def event():
    return "event:" + uuid4().hex

def prepare(client, *, locked=False):
    owner = profile(client, lock_guided=locked)
    owner, spec, url = offer(client, owner=owner, acknowledge=True)
    return owner, spec, url

def get(client, url):
    r = client.get(url + "/views")
    assert r.status_code == 200, r.text
    return r.json()

def body(s, *, operation="adjust", configuration=None):
    if configuration is None and operation == "adjust":
        configuration = next(c for c in s["feasible_configurations"] if c != s["spec"]["configuration"])
    if configuration is not None:
        configuration = {k: v for k, v in configuration.items() if k != "configuration_id"}
    return dict(request_id=event(), expected_revision=s["ledger"]["revision"], parent_view_id=s["active_view_id"], operation=operation,
                configuration=configuration, focus_action_id=s["focus_action_id"])

def change(client, url, s, **kwargs):
    request = body(s, **kwargs)
    r = client.post(url + "/views", json=request)
    assert r.status_code == 200, r.text
    return r.json(), request

def display(client, url, s):
    request = dict(event_id=event(), expected_revision=s["ledger"]["revision"], view_id=s["active_view_id"], action_id=s["focus_action_id"])
    r = client.post(url + "/views/display", json=request)
    assert r.status_code == 200, r.text
    return r.json(), request

def test_original_read_and_adjust_never_change_policy_or_original_records(tmp_path):
    app = backend(tmp_path)
    with TestClient(app) as client:
        _, root, url = prepare(client)
        before = app.state.runtime.export_state()
        s = get(client, url)
        assert s["learning_eligible"] and not s["ledger"]["views"]
        s, _ = change(client, url, s)
        assert not s["learning_eligible"]
        assert app.state.runtime.export_state() == before
        assert client.get(url).json()["spec"] == root
        assert client.get(url + "/pipeline-trace").json()["adjustments"]["ledger"] == s["ledger"]

def test_required_source_and_frozen_explanation_preserved_for_every_feasible_view(tmp_path):
    with TestClient(backend(tmp_path)) as client:
        _, root, url = prepare(client)
        initial = get(client, url)
        for configuration in initial["feasible_configurations"]:
            s = get(client, url)
            if configuration == s["spec"]["configuration"]:
                continue
            s, _ = change(client, url, s, configuration=configuration)
            assert s["spec"]["explanation"]["source"] == root["explanation"]["source"]
            assert s["spec"]["explanation"]["explanations"] == root["explanation"]["explanations"]
            assert {json.dumps(c["source"], sort_keys=True) for c in s["spec"]["cards"]} == {json.dumps(c["source"], sort_keys=True) for c in root["cards"]}
            protected = root["explanation"]["source"]["preservation"]["always_visible"]
            assert all(ref in s["spec"]["visibility"]["visible"] for ref in protected)

def test_undo_creates_new_identity_and_restores_prior_layout(tmp_path):
    with TestClient(backend(tmp_path)) as client:
        _, root, url = prepare(client)
        s, _ = change(client, url, get(client, url))
        first = s
        choices = [c for c in s["feasible_configurations"] if c != s["spec"]["configuration"] and c != root["configuration"]]
        s, _ = change(client, url, s, configuration=choices[0])
        s, _ = change(client, url, s, operation="undo")
        assert s["spec"]["configuration"] == first["spec"]["configuration"]
        assert s["active_view_id"] != first["active_view_id"] and not s["displayed_action_ids"]
        s, _ = change(client, url, s, operation="undo")
        assert s["spec"]["configuration"] == root["configuration"]
        assert not s["can_undo"] and not s["learning_eligible"]
        assert client.post(url + "/feedback", json=feedback_body(root)).status_code == 409

def test_display_and_rating_are_idempotent_and_not_shared_learning(tmp_path):
    app = backend(tmp_path)
    with TestClient(app) as client:
        _, root, url = prepare(client)
        before = client.get("/dev/v1/policy").json()
        s, request = change(client, url, get(client, url))
        assert client.post(url + "/views", json=request).json()["ledger"] == s["ledger"]
        rating = dict(event_id=event(), expected_revision=s["ledger"]["revision"], view_id=s["active_view_id"], rating="about_right")
        assert client.post(url + "/views/rating", json=rating).status_code == 409
        s, shown = display(client, url, s)
        assert client.post(url + "/views/display", json=shown).json()["ledger"] == s["ledger"]
        rating["expected_revision"] = s["ledger"]["revision"]
        r = client.post(url + "/views/rating", json=rating)
        assert r.status_code == 200, r.text
        assert r.json()["ledger"]["ratings"][0]["learning_eligible"] is False
        assert client.post(url + "/views/rating", json=rating).json() == r.json()
        assert client.post(url + "/views/rating", json={**rating, "rating": "need_more"}).status_code == 409
        assert client.post(url + "/feedback", json=feedback_body(root)).status_code == 409
        after = client.get("/dev/v1/policy").json()
        assert before == after

def test_stale_revision_parent_conflict_and_reused_identity(tmp_path):
    with TestClient(backend(tmp_path)) as client:
        _, _, url = prepare(client)
        initial = get(client, url)
        s, request = change(client, url, initial)
        stale = body(initial)
        assert client.post(url + "/views", json=stale).status_code == 409
        assert client.post(url + "/views", json={**request, "focus_action_id": "action:invalid"}).status_code == 409
        wrong_parent = body(s); wrong_parent["parent_view_id"] = "original"
        assert client.post(url + "/views", json=wrong_parent).status_code == 409

def test_hard_locks_and_unavailable_diagrams_are_not_overridden(tmp_path):
    with TestClient(backend(tmp_path)) as client:
        _, _, url = prepare(client, locked=True)
        s = get(client, url)
        assert all(c["presentation_mode"] == "GUIDED" and c["relationship_visual"] not in {"BRANCH_MAP", "PARALLEL_MAP"} for c in s["feasible_configurations"])
        request = body(s)
        request["configuration"]["presentation_mode"] = "OVERVIEW"
        # Configuration ID is a computed server field, never client-authoritative.
        request["configuration"].pop("configuration_id", None)
        assert client.post(url + "/views", json=request).status_code == 409

def test_cross_session_missing_and_no_undo_fail_closed(tmp_path):
    with TestClient(backend(tmp_path)) as client:
        _, _, url = prepare(client)
        s = get(client, url)
        assert client.post(url + "/views", json=body(s, operation="undo")).status_code == 409
        other = profile(client)
        foreign = session_base(other["session"]) + "/presentations/" + s["ledger"]["exposure_id"]
        assert client.get(foreign + "/views").status_code == 404
        assert client.post(foreign + "/views", json=body(s)).status_code == 404

def test_preferences_explicit_idempotent_and_leave_hard_settings_and_policy_unchanged(tmp_path):
    with TestClient(backend(tmp_path)) as client:
        owner, _, url = prepare(client)
        before = client.get("/dev/v1/policy").json()
        s, _ = change(client, url, get(client, url))
        old_session = client.get(session_base(owner["session"])).json()
        assert old_session["settings"] == owner["session"]["settings"]
        s, _ = display(client, url, s)
        request = dict(request_id=event(), view_id=s["active_view_id"], expected_session_revision=old_session["revision"])
        response = client.post(url + "/views/preferences", json=request)
        assert response.status_code == 200, response.text
        saved = response.json()
        for key in ("locks", "accessibility", "familiarity", "navigation_capability"):
            assert saved["settings"][key] == old_session["settings"][key]
        assert client.post(url + "/views/preferences", json=request).json() == saved
        assert get(client, url)["stale_for_display"]
        assert client.get("/dev/v1/policy").json() == before

def test_restart_recovers_views_displays_and_ratings_without_policy_migration(tmp_path):
    def app():
        return create_app(provider=FakeProvider(failure="offline"), database_path=tmp_path / "main.sqlite3", policy_config=config(), allow_legacy_adaptive_sessions=False)
    with TestClient(app()) as client:
        _, _, url = prepare(client)
        s, _ = change(client, url, get(client, url))
        s, _ = display(client, url, s)
        before = get(client, url)
        policy = client.get("/dev/v1/policy").json()
    with TestClient(app()) as client:
        assert get(client, url) == before
        assert client.get("/dev/v1/policy").json() == policy

def test_corrupt_sidecar_blocks_reads_and_original_rewards(tmp_path):
    app = backend(tmp_path)
    with TestClient(app) as client:
        _, root, url = prepare(client)
        change(client, url, get(client, url))
        app.state.runtime.adjustments.connection.execute("UPDATE c4_view_ledgers SET checksum='invalid'")
        assert client.get(url + "/views").status_code == 503
        assert client.post(url + "/feedback", json=feedback_body(root)).status_code == 503

def test_reused_operation_body_and_event_ids_rejected(tmp_path):
    with TestClient(backend(tmp_path)) as client:
        _, _, url = prepare(client)
        s, request = change(client, url, get(client, url))
        assert client.post(url + "/views", json={**request, "expected_revision": request["expected_revision"] + 1}).status_code == 409
        s, shown = display(client, url, s)
        rating = dict(event_id=shown["event_id"], expected_revision=s["ledger"]["revision"], view_id=s["active_view_id"], rating="about_right")
        assert client.post(url + "/views/rating", json=rating).status_code == 409

def test_new_original_navigation_is_blocked_after_a_manual_view(tmp_path):
    with TestClient(backend(tmp_path)) as client:
        owner, root, url = prepare(client)
        change(client, url, get(client, url))
        request = dict(event_id=event(), expected_revision=client.get(session_base(owner["session"])).json()["revision"],
            presentation_id=root["presentation_id"], configuration_id=root["configuration"]["configuration_id"], action_id=root["pages"][-1]["action_id"])
        assert client.post(url + "/navigation", json=request).status_code == 409

def test_existing_policy_receipt_survives_later_manual_views_without_relearning(tmp_path):
    with TestClient(backend(tmp_path)) as client:
        _, root, url = prepare(client)
        receipt = client.post(url + "/feedback", json=feedback_body(root)).json()
        before = client.get("/dev/v1/policy").json()
        change(client, url, get(client, url))
        assert client.post(url + "/feedback", json=feedback_body(root)).json() == receipt
        assert client.get("/dev/v1/policy").json() == before
