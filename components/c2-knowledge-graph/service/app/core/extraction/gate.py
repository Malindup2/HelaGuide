"""A free check before the model: is there anything on this page worth paying to read?

The crawler does not know what it saved. A language-picker homepage and a fee table look the
same to it. This runs on the saved Markdown, costs nothing, and only skips a page that has
NO fee, document or prerequisite wording at all, or is a stub of a few lines. It is deliberately
conservative: a page with even one signal goes to the model.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.acquisition.discover import score_text, strip_menus

MIN_CHARS = 300  # readable characters after the site menu is removed: below this is a stub


@dataclass(frozen=True)
class GateVerdict:
    send: bool
    reason: str
    chars: int
    signals: str  # F, D, P flags as in discovery


def should_extract(text: str) -> GateVerdict:
    body = strip_menus(text)
    chars = len(" ".join(body.split()))
    sig = score_text(body)
    if chars < MIN_CHARS:
        return GateVerdict(False, f"almost no readable text ({chars} characters)", chars, sig.flags)
    if sig.score == 0:
        return GateVerdict(False, "no fee, document or prerequisite wording", chars, sig.flags)
    return GateVerdict(True, "has facts to read", chars, sig.flags)  # a short page WITH a signal is kept
