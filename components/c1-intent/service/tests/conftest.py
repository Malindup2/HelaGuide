import json

import pytest
from fastapi.testclient import TestClient

from helaguide_common.config import get_settings
from helaguide_common.examples import load_example

from app.core import pipeline
from app.core.dst import is_sinhala, words_with_offsets
from app.core.engine import C1Engine, Session
from app.core.sessions import SessionStore
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def example():
    return load_example


@pytest.fixture(scope="session")
def intent_schema():
    path = get_settings().contracts_dir / "schema" / "v1" / "intent.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


class FakeEngine:
    """Stands in for C1Engine without torch: fixed intents per message, real Session and state tracker."""

    def __init__(self, intents, min_confidence, fallback):
        self.intents = intents                  # text -> (intent, confidence)
        self.min_confidence = min_confidence
        self.fallback = fallback
        self.use_ner = False

    def tag_languages(self, text):
        return [(w, "SI" if is_sinhala(w) else "EN") for w, _, _ in words_with_offsets(text)]

    def classify_intent(self, user_turns):
        return self.intents.get(user_turns[-1], ("nic_replace_lost", 0.9))

    language_of = staticmethod(C1Engine.language_of)

    def new_session(self):
        return Session(self)


@pytest.fixture
def real_mode(monkeypatch, tmp_path):
    """STUB_MODE=false with a fake engine and an empty session store. Returns the text -> intent table."""
    intents = {}
    (tmp_path / "c1_config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("STUB_MODE", "false")
    monkeypatch.setenv("C1_MODEL_DIR", str(tmp_path))
    monkeypatch.delenv("C1_MIN_CONFIDENCE", raising=False)
    monkeypatch.setattr(pipeline, "_engine", None)
    monkeypatch.setattr(pipeline, "_store", SessionStore())
    monkeypatch.setattr(pipeline, "_load_engine", lambda path: FakeEngine(
        intents, pipeline.min_confidence(), pipeline.unsupported_service_fallback))
    return intents
