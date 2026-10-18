"""
C1 entry point. Stub mode returns contracts/examples/intent.example.json; real mode runs the engine
(language tags -> intent -> slots -> dialogue state) and projects the state onto the `intent` contract.
"""
import logging
import os
import threading
from pathlib import Path

from helaguide_common.config import get_settings
from helaguide_common.contracts import Intent, UtteranceRequest
from helaguide_common.examples import load_example

from app.core.dst import SERVICES, gaz_find
from app.core.projection import project
from app.core.sessions import SessionStore

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


def _step(session_id: str, text: str, bot_text: str | None = None) -> dict:
    engine = get_engine()
    result = _store.step(session_id, engine.new_session, text, bot_text)
    source = result.get("intent_source", "model")
    if source != "model":
        # no message text in logs (privacy)
        log.info("low confidence: session=%s turn=%s model=%s conf=%.4f < %.2f -> %s (%s)",
                 session_id, result["turn_id"], result["intent_model_output"], result["intent_confidence"],
                 getattr(engine, "min_confidence", float("nan")), result["intent"], source)
    return result


def resolve(req: UtteranceRequest) -> Intent:
    if get_settings().stub_mode:
        sample = load_example("intent")
        return Intent(**{**sample, "session_id": req.session_id})
    # the contract request carries no bot text, so the tracker reads the message on its own
    result = _step(req.session_id, req.text)
    return project(result, req.session_id, req.text)
