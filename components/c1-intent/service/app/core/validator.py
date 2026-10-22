"""
Validator for the LLM dialogue layer: every update the LLM proposes is checked here before it touches the session
state. The LLM never writes state directly. Values are checked and canonicalised with the tracker's own helpers
(dst.py), so a slot filled by the LLM looks exactly like one filled by the rules.

Two steps, because the slot frame depends on the intent:
  check_turn(llm, nlu_intent)       -> TurnCheck: dialogue act, intent (falls back to XLM-R), tasks, reply
  merge_slots(intent, updates, ...) -> SlotMerge: the new slots of that intent, with rejections and conflicts

Slot rules:
  - the slot must belong to the intent (INTENT_SLOTS); null / empty values mean "not mentioned" and are skipped
  - district    district gazetteer (25 districts, EN / romanized / SI), else a known town -> its district
  - date slots  an ISO date YYYY-MM-DD (what the prompt asks for) that exists on the calendar; otherwise the
                date matcher must find a date in the value ("mid December", "ලබන මාසේ")
  - enums       applicant_for, change_field, urgency, service_type: the canonical value or one of its keywords
  - purpose, issue  their taxonomy (PURPOSES, ISSUES) if one matches, else "other" with the raw text in `raw`;
                a bare "other" takes its raw text from the LLM's slot_raw, else from the user's message
  - service_mentioned  the service gazetteer if one matches, else the text; new_value: the text
  - "unknown" (the citizen does not know) is accepted for any slot
Conflicts (the rules tracker and the LLM set the same slot this turn to different values): the rules value is
kept when it came from an extractive match (district gazetteer / town, date matcher), else the LLM value wins.
applicant_for, once known, changes only when the dialogue act is "correction". This always holds for the LLM; for
the rules tracker only with protect_rules=True (C1_PROTECT_APPLICANT_FOR, so the evaluation can separate the two).
`ready` is recomputed from missing_slots; the LLM's ready_to_confirm counts only when nothing is missing.
"""
import logging
import re
from dataclasses import dataclass, field
from datetime import date

from app.core.dst import (APPLICANT, CHANGE_FIELD, DATE_SLOTS, INTENT_SLOTS, ISSUES, NORMAL, PURPOSES, SERVICES,
                         UNKNOWN_VALUE, URGENT, canon_value, find_date, find_district, find_town, gaz_find, has_any,
                         words_with_offsets)

log = logging.getLogger("c1-intent")

INTENTS = frozenset(INTENT_SLOTS)       # the 12 internal intents
DIALOGUE_ACTS = ("greet", "new_request", "slot_answer", "correction", "confirm", "deny", "chitchat", "out_of_scope")
EXTRACTIVE_SLOTS = frozenset({"district"} | DATE_SLOTS)    # rules values that come from a gazetteer / date match
PROTECTED_SLOTS = ("applicant_for",)
OTHER = "other"
MAX_VALUE_CHARS = 120
MAX_REPLY_CHARS = 1000

ENUMS = {   # slot -> [(canonical value, keywords)], checked in order
    "applicant_for": APPLICANT,
    "change_field": CHANGE_FIELD,
    "urgency": [("normal", NORMAL), ("urgent", URGENT + ["one_day"])],
    "service_type": [("normal", NORMAL), ("urgent", URGENT + ["one_day"])],
}
TAXONOMIES = {"purpose": PURPOSES, "issue": ISSUES}     # no match -> "other" + raw text
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class Rejected(ValueError):
    """A proposed value failed a check; the message is the reason code."""


@dataclass
class Rejection:
    field: str          # a slot name, or "active_intent", "dialogue_act", "tasks", "reply", "ready_to_confirm"
    value: object
    reason: str
    source: str = "llm"


@dataclass
class Conflict:
    slot: str
    rules: str
    llm: str
    kept: str           # "rules" or "llm"
    reason: str


@dataclass
class TurnCheck:
    dialogue_act: str | None
    intent: str                     # the validated internal intent of this turn
    intent_source: str              # "llm", or "nlu_fallback" when the LLM's intent was missing or invalid
    tasks: list[str]
    reply: str | None               # None: the caller uses the rules reply
    ready_claim: bool
    rejections: list[Rejection] = field(default_factory=list)


@dataclass
class SlotMerge:
    slots: dict[str, str]
    accepted: dict[str, str]        # LLM updates that passed the checks (canonical values)
    raw: dict[str, str]             # slot -> the LLM's text, when the value was stored as "other"
    missing_slots: list[str]
    ready: bool                     # every slot of the intent is filled (recomputed, never the LLM's claim)
    proposed: int                   # LLM slot updates with a value (the denominator of the rejection rate)
    rejections: list[Rejection] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)


# ---------------------------------------------------------------- turn-level fields
def check_turn(llm: dict, nlu_intent: str) -> TurnCheck:
    """Dialogue act, intent, tasks and reply from the LLM's JSON. A bad intent falls back to the XLM-R intent."""
    rejections = []
    act = llm.get("dialogue_act")
    if act not in DIALOGUE_ACTS:
        rejections.append(Rejection("dialogue_act", act, "unknown_act"))
        act = None

    intent, source = llm.get("active_intent"), "llm"
    if intent not in INTENTS:
        if intent is not None:      # null = no request yet (a greeting): not a mistake, nothing to reject
            rejections.append(Rejection("active_intent", intent, "unknown_intent"))
        intent, source = (nlu_intent if nlu_intent in INTENTS else "unknown"), "nlu_fallback"

    tasks, raw_tasks = [], llm.get("tasks") or []
    if not isinstance(raw_tasks, list):
        rejections.append(Rejection("tasks", raw_tasks, "not_a_list"))
        raw_tasks = []
    for t in raw_tasks:
        if t not in INTENTS:
            rejections.append(Rejection("tasks", t, "unknown_intent"))
        elif t not in tasks:
            tasks.append(t)

    reply = llm.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        rejections.append(Rejection("reply", reply, "empty_reply"))
        reply = None
    elif len(reply) > MAX_REPLY_CHARS:
        rejections.append(Rejection("reply", reply[:80], "too_long"))
        reply = None
    else:
        reply = reply.strip()

    ready_claim = llm.get("ready_to_confirm", False)
    if not isinstance(ready_claim, bool):
        rejections.append(Rejection("ready_to_confirm", ready_claim, "not_a_bool"))
        ready_claim = False
    return TurnCheck(act, intent, source, tasks, reply, ready_claim, rejections)


# ---------------------------------------------------------------- slot values
def canonical_value(slot: str, value) -> tuple[str, str | None]:
    """-> (canonical value, raw text kept for an "other" value, else None). Raises Rejected(reason)."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise Rejected("not_a_string")
    text = str(value).strip()
    if len(text) > MAX_VALUE_CHARS:
        raise Rejected("too_long")
    if text.lower() == UNKNOWN_VALUE:
        return UNKNOWN_VALUE, None
    words = list(words_with_offsets(text))
    if slot == "district":
        hit = find_district(words)
        if hit:
            return hit[2], None
        town = find_town(words)
        if town:
            return town[1], None
        raise Rejected("not_a_district")
    if slot in DATE_SLOTS:
        if _ISO_DATE.fullmatch(text):
            try:
                date.fromisoformat(text)
            except ValueError:
                raise Rejected("not_a_date") from None
            return text, None
        hit = find_date(words)
        if not hit:
            raise Rejected("not_a_date")
        return hit[0], None
    if slot in ENUMS:
        options = ENUMS[slot]
        if text.lower() in {canon for canon, _ in options}:
            return text.lower(), None
        for canon, forms in options:
            if has_any(words, forms):
                return canon, None
        raise Rejected("not_an_enum_value")
    if slot in TAXONOMIES:
        hit = gaz_find(text, TAXONOMIES[slot], words)
        if hit:
            return hit[0], None
        if text.lower() == OTHER:
            return OTHER, None
        return OTHER, text
    if slot == "service_mentioned":
        hit = gaz_find(text, SERVICES, words)
        return (hit[0] if hit else text), None
    return text, None       # new_value: free text


def _same(slot, a, b):
    return canon_value(slot, a) == canon_value(slot, b)


def merge_slots(intent: str, updates, act: str | None, prev: dict, rules_changes: dict | None = None,
                protect_rules: bool = True, raw_values=None, message: str | None = None) -> SlotMerge:
    """
    The intent's slots after this turn: prev, then the rules tracker's changes this turn (rules_changes; empty in
    llm-only mode), then the LLM's checked updates under the conflict policy.
    prev: the intent's slots before this turn. rules_changes: {slot: value} the tracker set or changed this turn.
    protect_rules: also undo a rules-tracker change to applicant_for without a correction (LLM changes always are).
    raw_values: the LLM's slot_raw ({slot: the user's words}); message: this turn's user text. Both only give the raw
    text of a bare "other" for purpose / issue.
    """
    rules_changes = dict(rules_changes or {})
    allowed = INTENT_SLOTS.get(intent, [])
    slots = {**prev, **rules_changes}
    accepted, raw, rejections, conflicts, proposed = {}, {}, [], [], 0
    if not isinstance(updates, dict):
        if updates not in (None, ""):
            rejections.append(Rejection("slot_updates", updates, "not_an_object"))
        updates = {}
    if not isinstance(raw_values, dict):
        if raw_values not in (None, ""):
            rejections.append(Rejection("slot_raw", raw_values, "not_an_object"))
        raw_values = {}

    for slot, value in updates.items():
        if value is None or (isinstance(value, str) and not value.strip()):
            continue                                # "not mentioned"
        proposed += 1
        if slot not in allowed:
            rejections.append(Rejection(slot, value, "slot_not_in_intent"))
            continue
        try:
            canon, raw_text = canonical_value(slot, value)
        except Rejected as e:
            rejections.append(Rejection(slot, value, str(e)))
            continue
        if canon == OTHER and raw_text is None and slot in TAXONOMIES:
            raw_text = _raw_for_other(raw_values.get(slot), message)
        accepted[slot] = canon
        if slot in rules_changes and not _same(slot, rules_changes[slot], canon):
            rules_value = rules_changes[slot]
            if slot in EXTRACTIVE_SLOTS:
                conflicts.append(Conflict(slot, rules_value, canon, "rules", "extractive_match"))
                continue
            conflicts.append(Conflict(slot, rules_value, canon, "llm", "rules_not_extractive"))
        slots[slot] = canon
        if raw_text is not None:
            raw[slot] = raw_text
        else:
            raw.pop(slot, None)

    for slot in PROTECTED_SLOTS:
        old = prev.get(slot)
        if old in (None, UNKNOWN_VALUE) or slots.get(slot) == old or act == "correction":
            continue
        source = "llm" if accepted.get(slot) == slots.get(slot) else "rules"
        if source == "rules" and not protect_rules:
            continue
        rejections.append(Rejection(slot, slots.get(slot), "protected_without_correction", source))
        accepted.pop(slot, None)
        slots[slot] = old

    for c in conflicts:     # slot names and sources only: values can be personal (an address)
        log.info("validator conflict: intent=%s slot=%s kept=%s (%s)", intent, c.slot, c.kept, c.reason)
    missing = [s for s in allowed if s not in slots]
    return SlotMerge(slots, accepted, raw, missing, bool(allowed) and not missing, proposed, rejections, conflicts)


def _raw_for_other(raw, message):
    """The user's words for a bare "other": the LLM's slot_raw when it is real text, else the message itself."""
    if isinstance(raw, str) and raw.strip() and raw.strip().lower() != OTHER:
        return raw.strip()[:MAX_VALUE_CHARS]
    message = " ".join((message or "").split())
    return message[:MAX_VALUE_CHARS] or None


def confirm_ready(ready_claim: bool, ready: bool) -> tuple[bool, Rejection | None]:
    """ready_to_confirm: the LLM's claim, only when every slot is filled (`ready`, from missing_slots)."""
    if ready_claim and not ready:
        return False, Rejection("ready_to_confirm", True, "slots_missing")
    return ready_claim and ready, None
