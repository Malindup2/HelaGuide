"""Page fingerprints and change classification (stage 1).

Two independent fingerprints per page decide whether it is worth re-extracting:

* a SHA-256 digest of the noise-stripped text ("did the words change?")
* a SHA-256 digest of a collapsed DOM tag skeleton ("did the layout change?")

SimHash is recorded as a magnitude label only. It is never a gate: a one-token edit,
such as a fee going from LKR 10,000 to LKR 11,000, moves a SimHash by only a few bits,
and a similarity threshold would dismiss exactly the change this component exists to
catch. After noise stripping, any remaining text difference is a real change.

Ported from the research prototype (live_trial/scripts/change_monitor.py).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from enum import StrEnum


class ChangeKind(StrEnum):
    NEW = "NEW"
    UNCHANGED = "UNCHANGED"
    CONTENT_CHANGED = "CONTENT_CHANGED"
    STRUCTURE_CHANGED = "STRUCTURE_CHANGED"
    UNREACHABLE = "UNREACHABLE"


# --------------------------------------------------------------------------- noise
# Regions that change on their own without the service information changing:
# visitor counters, "last updated" stamps, session ids. They are stripped BEFORE
# hashing so they never register as a change.
#
# Every pattern consumes ONLY the noise token itself, anchored to a concrete shape (a
# date, a digit run) and never to arbitrary trailing text. An earlier greedy pattern ate
# 40 characters after "last updated" and deleted a fee from the sentence "The last
# updated fee schedule shows LKR 10,000". A filter that deletes real facts is far more
# dangerous than one that lets a counter through.
#
# Bare clock times are deliberately NOT stripped: "Office hours are 8:30 AM to 4:15 PM"
# is information a citizen needs, not page furniture.
_DATE = (
    r"(?:\d{1,2}[\s/\-\.]{1,3}\d{1,2}[\s/\-\.]{1,3}\d{2,4}"
    r"|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}"
    r"|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}"
    r"|\d{4}-\d{2}-\d{2})"
)

NOISE_PATTERNS = [
    rf"(?i)\blast\s+(?:updated?|modified)\s*:?\s*{_DATE}",
    r"(?i)\b(?:page\s+)?(?:visitors?|hits|views|visits)\s*:?\s*[\d,]+\b",
    r"(?i)\bcopyright\s*(?:&copy;|©)?\s*\d{4}",
    r"(?:&copy;|©)\s*\d{4}",
    r"(?i)\bsession[_\-]?id\s*[=:]\s*\w+",
    # A full timestamp (date AND time together) is furniture; a bare time is not.
    rf"(?i){_DATE}\s+\d{{1,2}}:\d{{2}}(?::\d{{2}})?\s*(?:am|pm)?",
]

# Unlabelled counters: immigration.gov.lk prints a bare hit counter in its footer.
_BARE_RUN = re.compile(r"(?<![\d,.\-/])\d{6,}(?![\d,.\-/])")
_CURRENCY_NEAR = re.compile(r"(?i)(?:rs\.?|lkr\.?)\s*$")
# A long digit run introduced by one of these words is an identifier the page states.
_LABEL_NEAR = re.compile(
    r"(?i)\b(?:nic|no|number|num|id|ref|reference|account|acc|passport|"
    r"licence|license|permit|registration|reg)\b\.?\s*[:#]?\s*$"
)


def _strip_bare_counters(text: str) -> str:
    def repl(m: re.Match) -> str:
        before = text[max(0, m.start() - 20) : m.start()]
        if _CURRENCY_NEAR.search(before[-14:]):
            return m.group(0)  # a fee: keep it
        if "+" in before:
            return m.group(0)  # part of a phone number: keep it
        if _LABEL_NEAR.search(before):
            return m.group(0)  # a stated identifier: keep it
        return " "

    return _BARE_RUN.sub(repl, text)


def strip_noise(text: str) -> str:
    """Remove self-changing regions (counters, timestamps) before hashing."""
    out = text or ""
    for pat in NOISE_PATTERNS:
        out = re.sub(pat, " ", out)
    return _strip_bare_counters(out)


def normalise_text(text: str) -> str:
    """Strip noise, then collapse whitespace so reflow is not a change."""
    return re.sub(r"\s+", " ", strip_noise(text)).strip()


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "ignore")).hexdigest()


# ----------------------------------------------------------------------- structure
def collapse_repeats(seq: list[str], max_span: int = 4) -> list[str]:
    """Run-length collapse repeated adjacent patterns: [li,/li,li,/li] -> [li,/li].

    This separates "they added a required document" from "they rebuilt the page".
    Adding one <li> adds tags, so a raw tag-sequence hash would call it structural, but
    the page's shape is identical. Collapsing repeats describes the template rather than
    the item count.
    """
    out = list(seq)
    changed = True
    while changed:
        changed = False
        for span in range(1, max_span + 1):
            i = 0
            res: list[str] = []
            while i < len(out):
                if i + 2 * span <= len(out) and out[i : i + span] == out[i + span : i + 2 * span]:
                    res.extend(out[i : i + span])
                    i += span
                    while i + span <= len(out) and out[i : i + span] == res[-span:]:
                        i += span
                    changed = True
                else:
                    res.append(out[i])
                    i += 1
            out = res
    return out


def structure_signature(html: str) -> str:
    """Ordered tag names with all text and attributes stripped, then collapsed.

    Same skeleton means same template even if every word differs. A different skeleton
    means the page was rebuilt, which breaks selector-based extraction and makes earlier
    facts provenance-uncertain.
    """
    tags = re.findall(r"<\s*(/?)([a-zA-Z][a-zA-Z0-9]*)", html or "")
    seq = [f"{slash}{name.lower()}" for slash, name in tags]
    return sha256(",".join(collapse_repeats(seq)))


# ------------------------------------------------------------------------- simhash
def simhash64(text: str) -> int:
    """Charikar SimHash over word 3-grams. Used as a magnitude label, never as a gate."""
    words = normalise_text(text).lower().split()
    if not words:
        return 0
    shingles = [" ".join(words[i : i + 3]) for i in range(max(1, len(words) - 2))]
    vector = [0] * 64
    for sh in shingles:
        h = int(hashlib.md5(sh.encode("utf-8", "ignore")).hexdigest()[:16], 16)
        for bit in range(64):
            vector[bit] += 1 if (h >> bit) & 1 else -1
    out = 0
    for bit in range(64):
        if vector[bit] > 0:
            out |= 1 << bit
    return out


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


# ------------------------------------------------------------------ classification
@dataclass(frozen=True)
class Fingerprint:
    content_hash: str
    structure_hash: str
    simhash: str  # 16 hex digits; text keeps it safe for JSON and a Postgres column
    char_count: int

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Fingerprint":
        return cls(d["content_hash"], d["structure_hash"], d["simhash"], int(d["char_count"]))


@dataclass(frozen=True)
class Classification:
    kind: ChangeKind
    detail: dict = field(default_factory=dict)


def fingerprint(text: str, html: str) -> Fingerprint:
    """Fingerprint a page from its extracted text and its raw HTML."""
    normalised = normalise_text(text)
    return Fingerprint(
        content_hash=sha256(normalised),
        structure_hash=structure_signature(html),
        simhash=f"{simhash64(text):016x}",
        char_count=len(normalised),
    )


def classify(prev: Fingerprint | None, cur: Fingerprint) -> Classification:
    """Compare this run's fingerprints with the stored ones."""
    if prev is None:
        return Classification(ChangeKind.NEW)

    same_content = prev.content_hash == cur.content_hash
    same_structure = prev.structure_hash == cur.structure_hash
    if same_content and same_structure:
        return Classification(ChangeKind.UNCHANGED)

    distance = hamming(int(prev.simhash, 16), int(cur.simhash, 16))
    detail: dict = {"simhash_distance": distance, "char_delta": cur.char_count - prev.char_count}

    # Structure is checked FIRST and independently of content: a page can be rebuilt
    # while its wording stays identical. That still breaks selector-based extraction, so
    # it must not be reported as unchanged just because the text matched.
    if not same_structure:
        detail["structure_changed"] = True
        detail["content_also_changed"] = not same_content
        return Classification(ChangeKind.STRUCTURE_CHANGED, detail)

    detail["magnitude"] = "minor" if distance <= 4 else "moderate" if distance <= 16 else "major"
    return Classification(ChangeKind.CONTENT_CHANGED, detail)
