"""The citizen console (page + /internal/demo routes), driven the way the page drives them."""
import json

import pytest

from app.core.pipeline import set_pipeline
from tests.helpers import make_settings
from tests.pipeline_fixtures import pipe, settings  # noqa: F401

FEE = "svc:passport:fee:normal"
STORY = [("ft-A1", "anon-0001"), ("ft-A2", "anon-0002"), ("ft-A3", "anon-0003"),
         ("ft-A4", "anon-0004"), ("ft-A5", "anon-0005"), ("ft-A6", "anon-0006")]
DATA = make_settings().data_dir


@pytest.fixture
def real(monkeypatch, pipe):
    monkeypatch.setenv("STUB_MODE", "false")
    set_pipeline(pipe)
    yield pipe
    set_pipeline(None)


def facts(client):
    w = client.get("/internal/demo/workflow").json()
    return {f["fact_id"]: f for s in w["steps"] for f in s["facts"]}


def send(client, sample, persona=None):
    persona = persona or dict(STORY).get(sample) or "anon-0001"
    r = client.post("/internal/demo/feedback", json={"sample_id": sample, "persona_id": persona})
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------- the page
def test_the_page_is_served_and_branded(client):
    r = client.get("/ui")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    for must in ("HelaGuide", "helaguide.lk", "Give feedback", "How do I get a passport?", "Simulate official update"):
        assert must in r.text, must
    assert "http://" not in r.text.replace("http://localhost", "") and "https://" not in r.text      # nothing is loaded from the internet


def test_the_demo_routes_refuse_to_run_in_stub_mode(client, monkeypatch):
    monkeypatch.setenv("STUB_MODE", "true")
    for method, url, body in [("get", "/internal/demo/workflow", None), ("get", "/internal/demo/personas", None),
                              ("get", "/internal/demo/samples", None), ("get", f"/internal/demo/audit/{FEE}", None),
                              ("post", "/internal/demo/feedback", {"sample_id": "ft-A1", "persona_id": "anon-0001"}),
                              ("post", "/internal/demo/official-update", {}), ("post", "/internal/demo/reset", {})]:
        r = getattr(client, method)(url, **({"json": body} if body is not None else {}))
        assert r.status_code == 409, url


# --------------------------------------------------------- the workflow screen
def test_the_workflow_starts_with_every_fact_at_ninety_percent(client, real):
    w = client.get("/internal/demo/workflow").json()
    assert w["title"] == "How to get a passport"
    assert [s["name"] for s in w["steps"]] == ["National Identity Card", "Passport"]       # the NIC comes first
    fs = facts(client)
    assert len(fs) == 14 and all(f["confidence_pct"] == 90 and f["warning_code"] == "NONE" for f in fs.values())
    assert fs[FEE]["value"] == "LKR 11,000" and fs["svc:passport:processing_time:normal"]["value"] == "14 days"


def test_one_report_changes_only_the_disputed_fact(client, real):
    client.get("/internal/demo/workflow")
    r = send(client, "ft-A1")
    assert r["state"] == "grounded" and r["fact_id"] == FEE and r["ui"]["fact_label"] == "Passport · Fee, normal service"
    assert (r["confidence"]["old"], r["confidence"]["pct"]) == (0.9, 76)
    after = facts(client)
    assert {k for k, f in after.items() if f["confidence_pct"] != 90} == {FEE}


def test_the_story_through_the_console_matches_the_terminal_demo(client, real):
    client.get("/internal/demo/workflow")
    out = [send(client, s, p) for s, p in STORY]
    assert [o["confidence"]["pct"] for o in out] == [76, 65, 60, 55, 60, 50]
    assert [o["exposure"]["warning_code"] for o in out] == ["NONE", "LOW_CONFIDENCE", "LOW_CONFIDENCE",
                                                            "LOW_CONFIDENCE", "LOW_CONFIDENCE", "VERIFY_BEFORE_VISIT"]
    assert out[3]["independence"]["I"] == pytest.approx(0.6)                    # the near-copy counts for less
    assert out[4]["kind"] == "support"
    assert facts(client)[FEE]["warning_code"] == "VERIFY_BEFORE_VISIT"


def test_translated_samples_use_the_saved_translation_so_the_demo_works_offline(client, real):
    client.get("/internal/demo/workflow")
    for sample, persona in [("ft-A5", "anon-0005"), ("ft-A3", "anon-0003")]:          # Sinhala and Singlish
        r = send(client, sample, persona)
        assert r["norm_backend"] == "cache" and r["state"] == "grounded"
        client.post("/internal/demo/reset", json={})
        client.get("/internal/demo/workflow")


def test_the_same_message_from_a_second_citizen_counts_as_a_copy(client, real):
    client.get("/internal/demo/workflow")
    send(client, "ft-A1", "anon-0001")
    again = send(client, "ft-A1", "anon-0002")
    assert again["independence"]["dup_count"] == 1 and again["independence"]["I"] == pytest.approx(0.6)


def test_the_screen_context_resolves_a_message_that_names_two_services(client, real):
    client.get("/internal/demo/workflow")                      # the citizen is looking at the passport workflow
    r = send(client, "ft-C8", "anon-0010")
    assert r["state"] == "grounded" and r["grounding"]["service_source"] == "context"
    assert r["fact_id"] == "svc:passport:document:birth_certificate"


def test_unclear_and_unlisted_messages_change_nothing_and_say_why(client, real):
    client.get("/internal/demo/workflow")
    unclear = send(client, "ft-D1", "anon-0014")
    assert unclear["state"] == "clarification_needed" and "could not tell which service" in unclear["ui"]["note"]
    unlisted = send(client, "ft-C10", "anon-0010")
    assert unlisted["state"] == "no_matching_fact" and "not listed" in unlisted["ui"]["note"]
    assert all(f["confidence_pct"] == 90 for f in facts(client).values())


# ------------------------------------------------- official update and reset
def test_the_official_update_resets_confidence_and_judges_the_reporters(client, real):
    client.get("/internal/demo/workflow")
    for s, p in STORY:
        send(client, s, p)
    reps = {p["id"]: p["reputation"] for p in client.get("/internal/demo/personas").json()}
    u = client.post("/internal/demo/official-update", json={}).json()
    passport = [c for c in u["changes"] if c["fact_id"] == FEE][0]
    assert (passport["old_value"], passport["new_value"], passport["confidence_pct"]) == ("LKR 11,000", "LKR 12,000", 90)
    outcome = {v["citizen"]: v["outcome"] for v in passport["verdicts"]}
    assert outcome["anon-0001"] == "verified_by_source" and outcome["anon-0005"] == "contradicted_by_source"
    f = facts(client)[FEE]
    assert (f["value"], f["confidence_pct"], f["warning_code"]) == ("LKR 12,000", 90, "VERIFIED_BY_SOURCE")
    after = {p["id"]: p["reputation"] for p in client.get("/internal/demo/personas").json()}
    assert after["anon-0001"] > reps["anon-0001"] and after["anon-0005"] < reps["anon-0005"]
    assert client.post("/internal/demo/official-update", json={}).json()["changes"] == []     # applying it twice changes nothing


def test_a_report_after_the_official_update_belongs_to_the_new_version(client, real):
    client.get("/internal/demo/workflow")
    client.post("/internal/demo/official-update", json={})
    r = send(client, "ft-A1", "anon-0001")
    assert r["state"] == "grounded" and r["confidence"]["old"] == 0.9            # the new version, not the closed one


def test_reset_gives_a_clean_start(client, real):
    client.get("/internal/demo/workflow")
    send(client, "ft-A1", "anon-0001")
    client.post("/internal/demo/official-update", json={})
    assert client.post("/internal/demo/reset", json={}).json() == {"ok": True}
    fs = facts(client)
    assert all(f["confidence_pct"] == 90 for f in fs.values()) and fs[FEE]["value"] == "LKR 11,000"
    assert send(client, "ft-A1", "anon-0001")["message_id"] == "ui-0001"           # the counter restarts too


# ----------------------------------------------------------- audit and samples
def test_the_audit_view_lists_versions_reports_and_reasons(client, real):
    client.get("/internal/demo/workflow")
    for s, p in STORY[:3]:
        send(client, s, p)
    a = client.get(f"/internal/demo/audit/{FEE}").json()
    assert a["label"] == "Passport · Fee, normal service" and len(a["versions"]) == 1
    assert len(a["versions"][0]["reports"]) == 3 and a["audit"][0]["reason"].startswith("initial confidence")
    assert [round(x["after"], 2) for x in a["audit"]] == [0.9, 0.76, 0.65, 0.6]
    assert client.get("/internal/demo/audit/svc:passport:fee:ghost").status_code == 404


def test_the_sample_list_is_complete_and_offline_safe(client, real):
    d = client.get("/internal/demo/samples").json()
    assert [g["id"] for g in d["groups"]] == ["english", "sinhala", "singlish", "other"]
    assert {s["language"] for s in d["samples"]} == {"en", "si", "mixed"} and len(d["samples"]) == 14
    cache = json.loads((DATA / "normalised_cache.json").read_text(encoding="utf-8"))
    from app.core.util import text_hash
    for s in d["samples"]:
        if s["language"] != "en":
            assert text_hash(s["text"]) in cache, s["id"]                      # every Sinhala/Singlish sample has a saved translation
    assert len(client.get("/internal/demo/personas").json()) == 11
    assert client.post("/internal/demo/feedback", json={"sample_id": "nope", "persona_id": "anon-0001"}).status_code == 404
    assert client.post("/internal/demo/feedback", json={"sample_id": "ft-A1", "persona_id": "nobody"}).status_code == 404


def test_every_sample_gives_the_outcome_in_the_answer_key(client, real):
    labels = {l["message_id"]: l for l in json.loads((DATA / "expected_labels.json").read_text(encoding="utf-8"))["labels"]}
    samples = client.get("/internal/demo/samples").json()["samples"]
    wrong = []
    for s in samples:
        client.post("/internal/demo/reset", json={})
        client.get("/internal/demo/workflow")
        r = send(client, s["id"], s["default_persona"])
        lab = labels[s["id"]]
        good = r["state"] == lab["expected_state"] and (r["state"] != "grounded" or r["fact_id"] == lab["expected_fact_id"])
        if not good:
            wrong.append(s["id"])
    # ft-J2 is the one message the tiny stand-in embedder cannot ground; the real model is checked with tune_grounding.
    assert set(wrong) <= {"ft-J2"}, wrong
