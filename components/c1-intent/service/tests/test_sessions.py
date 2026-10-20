"""Session store and real-mode wiring, with a fake engine (no torch, no model files)."""
import subprocess
import sys
from pathlib import Path

from app.core.sessions import SessionStore


def post(client, session_id, text):
    r = client.post("/v1/intent", json={"session_id": session_id, "text": text})
    assert r.status_code == 200, r.text
    return r.json()


def test_district_carries_over_in_same_session(client, real_mode):
    first = post(client, "anon-1", "mata ID eka nathi una")
    second = post(client, "anon-1", "Matara")
    assert (first["turn_id"], first["entities"]["district"]) == (0, None)
    assert (second["turn_id"], second["entities"]["district"]) == (1, "Matara")
    third = post(client, "anon-1", "ow ikmanata one")
    assert third["entities"]["district"] == "Matara"


def test_district_does_not_leak_to_other_session(client, real_mode):
    post(client, "anon-1", "mata ID eka nathi una")
    post(client, "anon-1", "Matara")
    other = post(client, "anon-2", "ow ikmanata one")
    assert other["turn_id"] == 0
    assert other["entities"]["district"] is None


def test_correction_replaces_district(client, real_mode):
    post(client, "anon-1", "mata ID eka nathi una")
    post(client, "anon-1", "Matara")
    assert post(client, "anon-1", "ne ne, Galle")["entities"]["district"] == "Galle"


def test_store_expires_idle_sessions():
    now = [0.0]
    store = SessionStore(ttl_s=60, clock=lambda: now[0])
    store.step("anon-a", FakeSession, "x")
    now[0] = 61
    store.step("anon-b", FakeSession, "x")
    assert "anon-a" not in store and "anon-b" in store


def test_store_caps_sessions_least_recent_first():
    store = SessionStore(max_sessions=2)
    store.step("anon-a", FakeSession, "x")
    store.step("anon-b", FakeSession, "x")
    store.step("anon-a", FakeSession, "x")      # anon-a is now the most recent
    store.step("anon-c", FakeSession, "x")
    assert len(store) == 2
    assert "anon-b" not in store and "anon-a" in store and "anon-c" in store


class FakeSession:
    def step(self, text, bot_text=None):
        return text


def test_low_confidence_unsupported_service_keyword_fallback(client, real_mode):
    real_mode["driving licence ekak ganna one"] = ("passport_new", 0.2)
    r = client.post("/v1/intent/details", json={"session_id": "anon-1", "text": "driving licence ekak ganna one"})
    d = r.json()
    assert (d["internal_intent"], d["intent_source"], d["route"]) == ("unsupported_service", "keyword_fallback", "fallback")


def test_low_confidence_keeps_topic_without_keyword(client, real_mode):
    real_mode["hmm"] = ("passport_new", 0.2)
    post(client, "anon-1", "mata ID eka nathi una")
    d = client.post("/v1/intent/details", json={"session_id": "anon-1", "text": "hmm"}).json()
    assert (d["internal_intent"], d["intent_source"]) == ("nic_replace_lost", "previous_topic")


def test_min_confidence_from_env(client, real_mode, monkeypatch):
    monkeypatch.setenv("C1_MIN_CONFIDENCE", "0.1")
    real_mode["passport ekak ganna one"] = ("passport_new", 0.2)
    d = client.post("/v1/intent/details", json={"session_id": "anon-1", "text": "passport ekak ganna one"}).json()
    assert (d["internal_intent"], d["intent_source"]) == ("passport_new", "model")


def test_missing_model_dir_is_503(client, monkeypatch, tmp_path):
    from app.core import pipeline
    monkeypatch.setenv("STUB_MODE", "false")
    monkeypatch.setenv("C1_MODEL_DIR", str(tmp_path / "missing"))
    monkeypatch.setattr(pipeline, "_engine", None)
    r = client.post("/v1/intent", json={"session_id": "anon-1", "text": "hi"})
    assert r.status_code == 503
    assert "C1_MODEL_DIR" in r.json()["detail"]


def test_app_imports_without_torch():
    code = "import sys, app.main, app.core.engine; assert 'torch' not in sys.modules; " \
           "assert 'transformers' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True, cwd=Path(__file__).resolve().parents[1])
