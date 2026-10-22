import pytest

from app.core.settings import DialogueSettings, SettingsError, dialogue_settings

ENV = ("C1_DIALOGUE_MODE", "C1_LLM_BASE_URL", "C1_LLM_MODEL", "C1_LLM_API_KEY", "C1_LLM_TIMEOUT",
       "C1_LLM_HISTORY_TURNS", "C1_LLM_JSON_MODE")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV:
        monkeypatch.delenv(name, raising=False)


def test_defaults_are_rules_mode_and_local_ollama():
    s = dialogue_settings()
    assert s == DialogueSettings()
    assert s.mode == "rules"
    assert s.base_url == "http://localhost:11434/v1"
    assert s.api_key == ""
    assert s.json_mode is True


def test_reads_env(monkeypatch):
    monkeypatch.setenv("C1_DIALOGUE_MODE", "Hybrid")
    monkeypatch.setenv("C1_LLM_BASE_URL", "https://example.test/v1/")
    monkeypatch.setenv("C1_LLM_MODEL", "qwen2.5")
    monkeypatch.setenv("C1_LLM_TIMEOUT", "12.5")
    monkeypatch.setenv("C1_LLM_HISTORY_TURNS", "4")
    monkeypatch.setenv("C1_LLM_JSON_MODE", "False")
    s = dialogue_settings()
    assert (s.mode, s.base_url, s.model, s.timeout, s.history_turns, s.json_mode) == \
        ("hybrid", "https://example.test/v1", "qwen2.5", 12.5, 4, False)


def test_api_key_is_not_in_repr(monkeypatch):
    monkeypatch.setenv("C1_LLM_API_KEY", "fake-key-123")
    s = dialogue_settings()
    assert s.api_key == "fake-key-123"
    assert "fake-key-123" not in repr(s)


@pytest.mark.parametrize("name, value", [("C1_DIALOGUE_MODE", "chatty"), ("C1_LLM_TIMEOUT", "soon"),
                                         ("C1_LLM_TIMEOUT", "0"), ("C1_LLM_HISTORY_TURNS", "-1"),
                                         ("C1_LLM_JSON_MODE", "maybe")])
def test_bad_values_raise(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(SettingsError, match=name):
        dialogue_settings()
