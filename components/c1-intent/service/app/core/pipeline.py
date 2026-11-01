"""
C1 entry point. Stub mode returns contracts/examples/intent.example.json; real mode runs the engine
(language tags -> intent -> slots -> dialogue state) and projects the state onto the `intent` contract.
"""
import logging
import os
import sqlite3
import threading
from pathlib import Path

from helaguide_common.config import get_settings
from helaguide_common.contracts import Intent, UtteranceRequest
from helaguide_common.examples import load_example

from app.core import completed
from app.core.dialogue import DialogueManager
from app.core.dst import INTENT_SLOTS, SERVICES, gaz_find
from app.core.llm_client import OpenAICompatClient
from app.core.projection import project
from app.core.sessions import SessionStore
from app.core.settings import SettingsError, dialogue_settings
from app.models.details import ChatRequest, ChatResponse, CompletedRequest, DetailsRequest, IntentDetails

COMPONENT_DIR = Path(__file__).resolve().parents[3]      # components/c1-intent/
DEFAULT_MODEL_DIR = "research/models/c1/run_v2_seed1"
DEFAULT_MIN_CONFIDENCE = 0.35
# services C1 does not handle (dst.SERVICES); naming one in a low-confidence turn means unsupported_service
UNSUPPORTED_SERVICES = {"driving license", "police clearance", "business registration", "building permit",
                        "utility connection", "residence certificate"}

log = logging.getLogger("c1-intent")


class EngineUnavailable(Exception):
    """The real engine cannot be loaded; the API answers 503 with this message."""


_engine = None
_engine_lock = threading.Lock()
_store = SessionStore()
# /v1/chat has its own conversations: a chat session never changes what /v1/intent returns for the same session_id
_chat_store = SessionStore()
_dialogue = None            # (settings, DialogueManager) for the current C1_DIALOGUE_MODE / C1_LLM_* settings
_dialogue_lock = threading.Lock()


def model_dir() -> Path:
    """C1_MODEL_DIR, absolute or relative to the working directory or to components/c1-intent/."""
    p = Path(os.environ.get("C1_MODEL_DIR") or DEFAULT_MODEL_DIR)
    if p.is_absolute() or p.exists():
        return p
    return COMPONENT_DIR / p


def min_confidence() -> float:
    raw = os.environ.get("C1_MIN_CONFIDENCE") or str(DEFAULT_MIN_CONFIDENCE)
    try:
        value = float(raw)
    except ValueError:
        raise EngineUnavailable(f"C1_MIN_CONFIDENCE must be a number between 0 and 1, got {raw!r}") from None
    if not 0 <= value <= 1:
        raise EngineUnavailable(f"C1_MIN_CONFIDENCE must be between 0 and 1, got {value}")
    return value


def unsupported_service_fallback(text: str) -> str | None:
    """Below the confidence threshold: a mention of a service C1 does not handle -> unsupported_service."""
    hit = gaz_find(text, SERVICES)
    return "unsupported_service" if hit and hit[0] in UNSUPPORTED_SERVICES else None


def _load_engine(path: Path):
    threshold = min_confidence()
    try:
        from app.core.engine import C1Engine
        # use_ner: rules first, XLM-R entities as fallback for free-text slots (best setting, Observation 10)
        engine = C1Engine(path, use_ner=True, min_confidence=threshold, fallback=unsupported_service_fallback)
    except ImportError as e:
        raise EngineUnavailable(
            f"C1 engine needs torch and transformers ({e}). Install them with: pip install -e \".[research]\""
        ) from e
    log.info("C1 engine loaded from %s, min_confidence=%.2f", path, threshold)
    return engine


def get_engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            path = model_dir()
            if not (path / "c1_config.json").is_file():
                raise EngineUnavailable(
                    f"C1 model folder not found: {path}. Set C1_MODEL_DIR to a folder with lid/, ner/, intent/ "
                    f"and c1_config.json (default {DEFAULT_MODEL_DIR}, relative to components/c1-intent/), "
                    "or set STUB_MODE=true."
                )
            _engine = _load_engine(path)
        return _engine


def warmup() -> None:
    """Real mode: load the models and run one throwaway turn so the first citizen's request is not slow."""
    if get_settings().stub_mode:
        return
    try:
        engine = get_engine()
    except EngineUnavailable as e:
        log.warning("C1 engine not loaded at startup: %s", e)
        return
    engine.new_session().step("mata passport ekak ganna one")
    log.info("C1 engine warmed up")


def _step(session_id: str, text: str, bot_text: str | None = None) -> dict:
    engine = get_engine()
    result = _store.step(session_id, engine.new_session, text, bot_text)
    source = result.get("intent_source", "model")
    if source in ("keyword_fallback", "previous_topic", "unknown"):
        # no message text in logs (privacy)
        log.info("low confidence: session=%s turn=%s model=%s conf=%.4f < %.2f -> %s (%s)",
                 session_id, result["turn_id"], result["intent_model_output"], result["intent_confidence"],
                 getattr(engine, "min_confidence", float("nan")), result["intent"], source)
    log.info("session=%s turn=%s intent=%s source=%s active=%s route=%s latency_ms=%.1f",
             session_id, result["turn_id"], result["intent"], source, result["active_intent"], result["route"],
             result["latency_ms"])
    _save_completed(session_id, "intent", result)
    return result


def _save_completed(session_id: str, endpoint: str, state: dict) -> None:
    """Save the turn's completed requests (app/core/completed.py). A storage error is logged, never fails the turn."""
    try:
        store = completed.get_store()
        if store and store.record(session_id, endpoint, state):
            log.info("completed request saved: session=%s endpoint=%s turn=%s", session_id, endpoint, state["turn_id"])
    except (sqlite3.Error, OSError) as e:
        log.warning("completed request not saved: session=%s (%s)", session_id, type(e).__name__)


def completed_requests(session_id: str | None = None, endpoint: str | None = None, intent: str | None = None,
                       limit: int = 50) -> list[CompletedRequest]:
    """Saved completed requests, newest first; empty when saving is off (C1_COMPLETED_DB=off)."""
    store = completed.get_store()
    if store is None:
        return []
    try:
        rows = store.list(session_id, endpoint, intent, limit)
    except (sqlite3.Error, OSError) as e:
        raise EngineUnavailable(f"completed requests store cannot be read ({type(e).__name__})") from None
    return [CompletedRequest(**r) for r in rows]


def resolve(req: UtteranceRequest) -> Intent:
    if get_settings().stub_mode:
        sample = load_example("intent")
        return Intent(**{**sample, "session_id": req.session_id})
    # the contract request carries no bot text, so the tracker reads the message on its own
    result = _step(req.session_id, req.text)
    return project(result, req.session_id, req.text)


def resolve_details(req: DetailsRequest) -> IntentDetails:
    """Full C1 analysis for one turn (C1-only, for the demo and C3). Same session store as resolve()."""
    if get_settings().stub_mode:
        return _stub_details(req)
    result = _step(req.session_id, req.text, req.bot_text)
    return IntentDetails(
        session_id=req.session_id,
        turn_id=result["turn_id"],
        state_version=result["state_version"],
        internal_intent=result["intent"],
        intent_model_output=result["intent_model_output"],
        confidence=result["intent_confidence"],
        intent_source=result["intent_source"],
        active_intent=result["active_intent"],
        intent_locked=result["intent_locked"],
        ready=result["ready"],
        assumed_slots=result["assumed_slots"],
        variant_pending=result["variant_pending"],
        reply=result["reply"],
        completed_requests=result["completed_requests"],
        pending_requests=result["pending_requests"],
        route=result["route"],
        slots=result["slots"],
        conditions=result["conditions"],
        missing_slots=result["missing_slots"],
        language=result["language"],
        language_tags=result["language_tags"],
        code_switched=result["code_switched"],
        latency_ms=result["latency_ms"],
        context_strategy=result["context_strategy"],
        context_tokens=result["context_tokens"],
        intent=project(result, req.session_id, req.text),
    )


def _stub_details(req: DetailsRequest) -> IntentDetails:
    """Canned details matching contracts/examples/intent.example.json (a passport application)."""
    intent = resolve(req)
    slots = {"district": intent.entities.district} if intent.entities.district else {}
    return IntentDetails(
        session_id=req.session_id,
        turn_id=intent.turn_id,
        state_version=0,
        internal_intent="passport_new",
        intent_model_output="passport_new",
        confidence=intent.confidence,
        intent_source="model",
        active_intent="passport_new",
        intent_locked=False,
        ready=False,
        assumed_slots=[],
        reply="Normal da urgent da?",
        completed_requests=[],
        pending_requests=[],
        route="orchestration",
        slots=slots,
        missing_slots=[s for s in INTENT_SLOTS["passport_new"] if s not in slots],
        language=intent.language,
        language_tags=[],
        code_switched=intent.language == "mixed",
        latency_ms=0.0,
        context_strategy="window_3",
        context_tokens=0,
        intent=intent,
    )


# ---------------------------------------------------------------- POST /v1/chat (C1-only)
def dialogue_manager() -> DialogueManager:
    """The manager for the current settings, rebuilt when they change. One LLM client per settings, so what it
    learns (JSON mode turned off by the provider) lasts across turns. A conversation keeps the manager it started
    with."""
    global _dialogue
    try:
        settings = dialogue_settings()
    except SettingsError as e:
        raise EngineUnavailable(f"C1 dialogue settings: {e}") from None
    with _dialogue_lock:
        if _dialogue is None or _dialogue[0] != settings:
            llm = None if settings.mode == "rules" else OpenAICompatClient.from_settings(settings)
            _dialogue = (settings, DialogueManager(llm, settings))
            log.info("dialogue mode=%s model=%s", settings.mode, settings.model if llm else "-")
        return _dialogue[1]


def resolve_chat(req: ChatRequest) -> ChatResponse:
    """One chat turn: the dialogue layer in C1_DIALOGUE_MODE (rules by default: the engine's own reply)."""
    if get_settings().stub_mode:
        return _stub_chat(req)
    manager = dialogue_manager()
    engine = get_engine()
    r = _chat_store.step(req.session_id, lambda: manager.new_session(engine.new_session()), req.text)
    st = r.state
    # no message text and no slot values in logs (privacy)
    log.info("chat session=%s turn=%s mode=%s source=%s%s intent=%s active=%s route=%s latency_ms=%.1f llm_ms=%.1f",
             req.session_id, st["turn_id"], r.dialogue_mode, r.dialogue_source, f" ({r.error})" if r.error else "",
             r.internal_intent, r.active_intent, r.route, r.latency_ms, r.llm_ms)
    _save_completed(req.session_id, "chat", st)
    return ChatResponse(
        session_id=req.session_id, turn_id=st["turn_id"], state_version=st["state_version"], reply=r.reply,
        dialogue_mode=r.dialogue_mode, dialogue_source=r.dialogue_source, dialogue_act=r.dialogue_act,
        internal_intent=r.internal_intent, intent_model_output=r.intent_model_output, confidence=r.confidence,
        intent_source=r.intent_source, active_intent=r.active_intent, tasks=r.tasks, slots=r.slots,
        raw_slots=r.raw_slots, missing_slots=r.missing_slots, assumed_slots=st["assumed_slots"], ready=r.ready,
        ready_to_confirm=r.ready_to_confirm, route=r.route, language=r.language, language_tags=r.language_tags,
        code_switched=r.code_switched, conflicts=r.conflicts, rejections=r.rejections, llm_proposed=r.llm_proposed,
        latency_ms=r.latency_ms, nlu_ms=r.nlu_ms, llm_ms=r.llm_ms, llm_usage=r.llm_usage, error=r.error,
        intent=project(st, req.session_id, req.text),
    )


def _stub_chat(req: ChatRequest) -> ChatResponse:
    """Stub mode: the canned passport turn of _stub_details, as a rules turn."""
    d = _stub_details(DetailsRequest(session_id=req.session_id, text=req.text))
    return ChatResponse(
        session_id=d.session_id, turn_id=d.turn_id, state_version=d.state_version, reply=d.reply,
        dialogue_mode="rules", dialogue_source="rules", dialogue_act=None, internal_intent=d.internal_intent,
        intent_model_output=d.intent_model_output, confidence=d.confidence, intent_source=d.intent_source,
        active_intent=d.active_intent, tasks=[d.active_intent], slots=d.slots, raw_slots={},
        missing_slots=d.missing_slots, assumed_slots=d.assumed_slots, ready=d.ready, ready_to_confirm=False,
        route=d.route, language=d.language, language_tags=d.language_tags, code_switched=d.code_switched,
        conflicts=[], rejections=[], llm_proposed=0, latency_ms=0.0, nlu_ms=0.0, llm_ms=0.0, llm_usage=None,
        error=None, intent=d.intent,
    )
