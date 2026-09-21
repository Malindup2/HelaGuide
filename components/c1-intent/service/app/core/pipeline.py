"""
C1 research logic lives in core/. Replace the stub with:
  language segmentation -> intent classification + entity extraction -> context handling.
"""
from helaguide_common.config import get_settings
from helaguide_common.contracts import Intent, UtteranceRequest
from helaguide_common.examples import load_example


def resolve(req: UtteranceRequest) -> Intent:
    if get_settings().stub_mode:
        sample = load_example("intent")
        return Intent(**{**sample, "session_id": req.session_id})
    raise NotImplementedError("C1 pipeline not implemented yet")
