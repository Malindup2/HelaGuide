"""
C1-only settings for the dialogue layer, read from the environment on every call (so tests can monkeypatch).
Kept inside C1 on purpose: shared/helaguide_common is common to all components.

C1_DIALOGUE_MODE   rules (default, the engine's own replies) | llm | hybrid (LLM + NLU hints + validator)
C1_LLM_BASE_URL    any OpenAI-compatible endpoint; default is a local Ollama
C1_LLM_MODEL       model name at that endpoint
C1_LLM_API_KEY     not needed for Ollama; never logged
C1_LLM_TIMEOUT     seconds per LLM request
C1_LLM_HISTORY_TURNS  conversation turns (user + bot) sent to the LLM
C1_LLM_JSON_MODE   true (default): ask for response_format json_object; false: rely on the prompt + JSON parsing
                   (the client also turns it off by itself when the provider rejects it)
C1_PROTECT_APPLICANT_FOR  true (default): in llm / hybrid mode the rules tracker may not change a known
                   applicant_for either, unless the turn is a correction (the LLM never may); false turns that off
                   for the rules side, so the evaluation can separate the LLM's effect from this tracker fix
"""
import os
from dataclasses import dataclass, field

DIALOGUE_MODES = ("rules", "llm", "hybrid")
DEFAULT_MODE = "rules"
DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "gemma3"
DEFAULT_TIMEOUT = 30.0
DEFAULT_HISTORY_TURNS = 6


class SettingsError(ValueError):
    """A C1_* dialogue setting has a value C1 cannot use."""


@dataclass(frozen=True)
class DialogueSettings:
    mode: str = DEFAULT_MODE
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    api_key: str = field(default="", repr=False)     # repr=False: never printed with the settings
    timeout: float = DEFAULT_TIMEOUT
    history_turns: int = DEFAULT_HISTORY_TURNS
    json_mode: bool = True
    protect_applicant_for: bool = True


def _env(name, default):
    return os.environ.get(name, "").strip() or default


def _flag(name, default):
    raw = _env(name, "true" if default else "false").lower()
    if raw in ("true", "1", "yes", "on"):
        return True
    if raw in ("false", "0", "no", "off"):
        return False
    raise SettingsError(f"{name} must be true or false, got {raw!r}")


def _number(name, default, cast, minimum):
    raw = _env(name, str(default))
    try:
        value = cast(raw)
    except ValueError:
        raise SettingsError(f"{name} must be a number, got {raw!r}") from None
    if value < minimum:
        raise SettingsError(f"{name} must be at least {minimum}, got {value}")
    return value


def dialogue_settings() -> DialogueSettings:
    mode = _env("C1_DIALOGUE_MODE", DEFAULT_MODE).lower()
    if mode not in DIALOGUE_MODES:
        raise SettingsError(f"C1_DIALOGUE_MODE must be one of {', '.join(DIALOGUE_MODES)}, got {mode!r}")
    return DialogueSettings(
        mode=mode,
        base_url=_env("C1_LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        model=_env("C1_LLM_MODEL", DEFAULT_MODEL),
        api_key=os.environ.get("C1_LLM_API_KEY", "").strip(),
        timeout=_number("C1_LLM_TIMEOUT", DEFAULT_TIMEOUT, float, 1),
        history_turns=_number("C1_LLM_HISTORY_TURNS", DEFAULT_HISTORY_TURNS, int, 0),
        json_mode=_flag("C1_LLM_JSON_MODE", True),
        protect_applicant_for=_flag("C1_PROTECT_APPLICANT_FOR", True),
    )
