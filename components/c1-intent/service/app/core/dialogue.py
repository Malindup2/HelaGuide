"""
LLM dialogue manager (C1_DIALOGUE_MODE = llm | hybrid). The engine and the rules tracker still run every turn;
the LLM writes the reply and proposes intent / slot updates; the validator decides what reaches the state.

One turn (hybrid):
  1. engine Session.step(): language tags, XLM-R intent, rules tracker -> the rules result (NLU hints + proposal)
  2. LLM: system prompt + last N turns + {state before the turn, NLU hints, message} -> JSON
  3. validator: check_turn (act, intent -> XLM-R fallback, tasks, reply), merge_slots (values, conflicts,
     applicant_for protection), confirm_ready
  4. the validated update is applied to a copy of the session state (see _apply), which then replaces it
  5. route, missing_slots and ready come from the engine's own _result(), as in rules mode
llm mode is the same without NLU hints and without the rules tracker's slot changes (an ablation).
rules mode, or any LLM / validation error: the rules result is used as it is (dialogue_source rules /
rules_fallback), so a failing LLM never breaks a turn.

The engine's Session is used as-is (engine.py is a copy of the research engine and is not changed here); its
private helpers (_switch_to, _load_state, _rename_request, _count_version, _result) keep the request lists, slot
frames and state_version consistent with rules mode.
"""
import copy
import logging
import time
from dataclasses import asdict, dataclass, field

from app.core.dst import (DATE_SLOTS, INTENT_SLOTS, KG_SERVICE_IDS, TOWN_DISTRICT, UNKNOWN_VALUE,
                         extract_conditions, merge_conditions)
from app.core.engine import ASK, CORE_INTENTS
from app.core.llm_client import LLM
from app.core.prompts import system_prompt, today_colombo, turn_message
from app.core.settings import DialogueSettings
from app.core.validator import (OTHER, Rejected, Rejection, canonical_value, check_turn, confirm_ready, is_iso_date,
                                merge_slots)

log = logging.getLogger("c1-intent")

NO_SLOT_ACTS = ("greet", "chitchat")    # with no slot change, reported like the engine's greeting turn (route none)


@dataclass
class DialogueResult:
    reply: str
    dialogue_act: str | None
    internal_intent: str            # this turn's intent ("unknown" when there is none)
    intent_model_output: str        # XLM-R before the confidence check
    confidence: float               # XLM-R
    intent_source: str              # rules: the engine's source; llm turns: "llm" or "nlu_fallback"
    active_intent: str | None
    tasks: list[str]                # active request first, then the unfinished ones
    slots: dict[str, str]
    raw_slots: dict[str, str]       # slot -> the user's words, for values stored as "other" and ISO dates
    missing_slots: list[str]
    ready: bool                     # from missing_slots, assumed slots and a pending variant (engine rule)
    ready_to_confirm: bool          # the LLM's claim, only when ready (False in rules mode)
    route: str
    language: str
    language_tags: list[dict]
    code_switched: bool
    dialogue_source: str            # llm | rules | rules_fallback
    dialogue_mode: str = "rules"    # C1_DIALOGUE_MODE of the manager that ran the turn
    conflicts: list[dict] = field(default_factory=list)
    rejections: list[dict] = field(default_factory=list)
    llm_proposed: int = 0           # LLM slot updates with a value (rejection-rate denominator)
    latency_ms: float = 0.0
    nlu_ms: float = 0.0
    llm_ms: float = 0.0
    llm_usage: dict | None = None   # prompt_tokens, completion_tokens, model, latency_ms, calls
    error: str | None = None        # exception class of a rules_fallback turn (never the message: privacy)
    state: dict = field(default_factory=dict, repr=False)   # the engine-style result, for contract projection


class ChatSession:
    """One /v1/chat conversation: the engine Session (all request state) plus the LLM layer's own memory."""

    def __init__(self, manager, engine_session):
        self.manager = manager
        self.session = engine_session
        self.history: list[dict] = []           # plain user / assistant turns, oldest first
        self.last_bot_text: str | None = None   # what the rules tracker reads as the bot's last question
        self.raw: dict[str, dict[str, str]] = {}    # intent -> {slot: user's words} for "other" values

    def step(self, text, bot_text=None):
        """SessionStore interface. bot_text is ignored: the conversation keeps its own last reply."""
        return self.manager.turn(self, text)


class DialogueManager:
    def __init__(self, llm: LLM | None, settings: DialogueSettings, today=today_colombo):
        self.llm = llm
        self.settings = settings
        self.today = today          # callable -> date (tests pin it)

    def new_session(self, engine_session) -> ChatSession:
        return ChatSession(self, engine_session)

    # ---------------------------------------------------------------- one turn
    def turn(self, chat: ChatSession, text: str) -> DialogueResult:
        t0 = time.perf_counter()
        mode = self.settings.mode
        before = _snapshot(chat.session)
        bot_text = chat.last_bot_text
        rules = chat.session.step(text, bot_text=bot_text)      # NLU + rules tracker, on the live session
        live = chat.session
        nlu_ms = _ms(t0)
        if mode == "rules":
            return self._rules_turn(chat, text, rules, "rules", t0, nlu_ms)
        if self.llm is None:
            return self._rules_turn(chat, text, rules, "rules_fallback", t0, nlu_ms, error="NoLLM")

        t1 = time.perf_counter()
        try:
            hints = self._hints(before, live, rules, text) if mode == "hybrid" else None
            gated = mode == "hybrid" and self.settings.hint_min_confidence > 0
            out = self.llm.complete_json(system_prompt(self.today(), weak_hints=gated),
                                         self._messages(chat, before, live.reply_lang, text, hints))
        except Exception as e:      # LLMError, or anything else: the demo must never crash because of the LLM
            log.warning("LLM failed (%s): rules_fallback for this turn", type(e).__name__)
            return self._rules_turn(chat, text, rules, "rules_fallback", t0, nlu_ms, llm_ms=_ms(t1),
                                    error=type(e).__name__)
        llm_ms = _ms(t1)
        try:
            work, result, checks = self._apply(chat, before, live, rules, out.data, text, bot_text, t0)
        except Exception as e:      # a validator or state bug must not break the turn either
            log.exception("LLM update could not be applied (%s): rules_fallback for this turn", type(e).__name__)
            return self._rules_turn(chat, text, rules, "rules_fallback", t0, nlu_ms, llm_ms=llm_ms,
                                    error=type(e).__name__)

        chat.session = work
        reply = result["reply"]
        chat.last_bot_text = checks["next_bot_text"] or reply
        chat.history += [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
        merge, turn = checks["merge"], checks["turn"]
        return DialogueResult(
            reply=reply, dialogue_act=turn.dialogue_act, internal_intent=result["intent"],
            intent_model_output=rules["intent_model_output"], confidence=rules["intent_confidence"],
            intent_source=turn.intent_source, active_intent=result["active_intent"], tasks=checks["tasks"],
            slots=result["slots"], raw_slots=dict(chat.raw.get(checks["intent"], {})),
            missing_slots=result["missing_slots"], ready=result["ready"],
            ready_to_confirm=checks["ready_to_confirm"], route=result["route"], language=result["language"],
            language_tags=result["language_tags"], code_switched=result["code_switched"], dialogue_source="llm",
            dialogue_mode=self.settings.mode,
            conflicts=[asdict(c) for c in merge.conflicts] if merge else [],
            rejections=[asdict(r) for r in checks["rejections"]],
            llm_proposed=merge.proposed if merge else 0,
            latency_ms=_ms(t0), nlu_ms=nlu_ms, llm_ms=llm_ms, llm_usage=asdict(out.usage), state=result)

    def _rules_turn(self, chat, text, rules, source, t0, nlu_ms, llm_ms=0.0, error=None) -> DialogueResult:
        """The engine's own turn, unchanged: rules mode, or the fallback when the LLM layer fails."""
        reply = rules["reply"]
        chat.last_bot_text = reply
        chat.history += [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
        return DialogueResult(
            reply=reply, dialogue_act=None, internal_intent=rules["intent"],
            intent_model_output=rules["intent_model_output"], confidence=rules["intent_confidence"],
            intent_source=rules["intent_source"], active_intent=rules["active_intent"], tasks=_tasks(chat.session),
            slots=rules["slots"], raw_slots={}, missing_slots=rules["missing_slots"], ready=rules["ready"],
            ready_to_confirm=False, route=rules["route"], language=rules["language"],
            language_tags=rules["language_tags"], code_switched=rules["code_switched"], dialogue_source=source,
            dialogue_mode=self.settings.mode,
            latency_ms=_ms(t0), nlu_ms=nlu_ms, llm_ms=llm_ms, error=error, state=rules)

    # ---------------------------------------------------------------- prompt
    def _messages(self, chat, before, reply_lang, text, hints):
        n = self.settings.history_turns
        past = chat.history[-2 * n:] if n else []
        active = before.active_intent
        state = {
            "active_intent": active,
            "slots": _public(before.states.get(active, {})) if active else {},
            "unconfirmed_slots": sorted(before.assumed.get(active, set()) & set(INTENT_SLOTS[active]))
                                 if active else [],
            "missing_slots": before._missing(active) if active else [],
            "carried_district": before.shared.get("district"),
            "tasks": _tasks(before),
            "reply_language_hint": reply_lang,      # a hint only (prompts.REPLY_LANGUAGE)
        }
        return [*past, {"role": "user", "content": turn_message(state, text, hints)}]

    def _hints(self, before, live, rules, text):
        """What XLM-R and the rules tracker made of this message (hybrid mode). With C1_HINT_MIN_CONFIDENCE above
        XLM-R's confidence the intent hints are marked weak; entities and slot changes are always sent."""
        intent = rules["intent"]
        old, new = before.states.get(intent, {}), live.states.get(intent, {})
        weak = rules["intent_confidence"] < self.settings.hint_min_confidence
        return {
            **({"intent_hint": "weak"} if weak else {}),
            "language_tags": " ".join(f"{t['word']}/{t['tag']}" for t in rules["language_tags"]),
            "xlmr_intent": rules["intent_model_output"],
            "xlmr_confidence": rules["intent_confidence"],
            "tracker_intent": intent,
            "entities": {k: text[v["start"]:v["end"]] for k, v in rules.get("slot_spans", {}).items()},
            "tracker_slot_updates": _public({k: v for k, v in new.items() if old.get(k) != v}),
            "tracker_missing_slots": rules["missing_slots"],
            "tracker_next_question": rules["reply"],
        }

    # ---------------------------------------------------------------- validated update
    def _apply(self, chat, before, live, rules, data, text, bot_text, t0):
        """-> (new session, engine-style result, checks). Works on a copy; the caller swaps it in."""
        mode = self.settings.mode
        turn = check_turn(data, rules["intent"])
        rejections = list(turn.rejections)
        intent, act = turn.intent, turn.dialogue_act
        no_slots = intent == "unknown"      # no request to attach slots to
        # start from the rules tracker's state only when it handled the same intent (hybrid). Otherwise the
        # validated LLM intent wins and the update starts from the state before the turn: a sticky XLM-R intent
        # ("driving license" read as birth_cert_copy) does not reach the state.
        agree = mode == "hybrid" and not no_slots and intent == rules["intent"]
        base = _snapshot(live if agree else before)
        if not agree:
            base.turns, base.history = list(live.turns), list(live.history)
            base.reply_lang, base.context_tokens = live.reply_lang, live.context_tokens
        base.offered = None         # the LLM's reply, not the rules reply, is what the citizen saw

        merge = None
        if no_slots:
            rejections += _remember_district(base, live if mode == "hybrid" else None, data.get("slot_updates"))
            intent_used = "none"
        else:
            intent_used = intent
            if intent in CORE_INTENTS:
                base._switch_to(intent)
                svc = KG_SERVICE_IDS[intent]
                provisional = base.variant_pending.get(svc)
                if provisional and provisional != intent:       # the LLM picked the variant
                    base._rename_request(provisional, intent)
                    del base.variant_pending[svc]
            if agree:
                prev = dict(before.states.get(intent, {}))
                frame = live.states.get(intent, {})
                rules_changes = {k: v for k, v in frame.items() if prev.get(k) != v}
                removed = set(prev) - set(frame)                # e.g. a carried district the citizen denied
                said = set()        # the rules step already took what was said out of `assumed`
            else:
                loaded = base._load_state(intent, text)
                prev = dict(loaded) if loaded is not None else dict(base.tracker.slots)
                frame = prev
                base.tracker.intent, base.tracker.slots = intent, dict(prev)
                base.tracker.conditions = merge_conditions(base.tracker.conditions, extract_conditions(text))
                extracted = {} if mode == "llm" else base.tracker.x.extract(text, intent, bot_text, prev)
                rules_changes = {k: v["value"] for k, v in extracted.items() if prev.get(k) != v["value"]}
                removed = set()
                said = set(extracted)
            # carried (assumed) values, e.g. a district from an earlier request or the first message
            carried = {k: frame[k] for k in base.tracker.assumed if k in frame}
            merge = merge_slots(intent, data.get("slot_updates"), act, prev, rules_changes,
                                protect_rules=self.settings.protect_applicant_for, raw_values=data.get("slot_raw"),
                                message=text)
            rejections += merge.rejections
            slots = merge.slots
            for k in removed - set(merge.accepted):
                slots.pop(k, None)
            # a carried value stays assumed until the citizen says it, gives another one, or answers the bot's
            # "still Galle?" (before.confirming): the LLM repeating the carried value does not confirm it
            changed = {k for k in merge.accepted if slots.get(k) != carried.get(k)}
            base.tracker.assumed -= said | changed
            confirming = before.confirming
            if confirming in base.tracker.assumed and act in ("confirm", "deny"):
                base.tracker.assumed.discard(confirming)
                if act == "deny":
                    slots.pop(confirming, None)
            if slots.get("town") and TOWN_DISTRICT.get(slots["town"]) != slots.get("district"):
                del slots["town"]                               # district changed to another one
            base.tracker.intent, base.tracker.slots = intent, dict(slots)
            base.states[intent] = dict(slots)
            base.assumed[intent] = set(base.tracker.assumed)
            base.conditions[intent] = dict(base.tracker.conditions)
            raw = chat.raw.setdefault(intent, {})
            for k in merge.accepted:            # a value set this turn replaces its old words, or has none
                raw.pop(k, None)
            raw.update(merge.raw)
            for k in list(raw):                 # words only for values still stored as other / an ISO date
                if not (slots.get(k) == OTHER or (k in DATE_SLOTS and is_iso_date(slots.get(k)))):
                    del raw[k]
            if act in NO_SLOT_ACTS and not merge.accepted and not rules_changes:
                intent_used = "none"    # a plain greeting / small talk: reported like the engine's greeting turn
        _sync_tasks(base, turn.tasks)

        asked = data.get("asks_slot")
        target = intent if intent_used != "none" else base.active_intent
        if asked is not None and asked not in INTENT_SLOTS.get(target, []):
            rejections.append(Rejection("asks_slot", asked, "slot_not_in_intent"))
            asked = None
        base.confirming = asked if asked in base.assumed.get(target, set()) else None
        base._count_version()

        tags = [(t["word"], t["tag"]) for t in rules["language_tags"]]
        reply = turn.reply or rules["reply"]
        result = base._result(text, t0, tags, rules["language"], rules["intent_model_output"], intent_used,
                              rules["intent_confidence"], turn.intent_source, reply)
        ready_to_confirm, bad_claim = confirm_ready(turn.ready_claim, result["ready"])
        if bad_claim:
            rejections.append(bad_claim)
        # the rules tracker reads the bot's question by its wording: give it the engine's own question
        next_bot_text = ASK[asked][base.reply_lang] if asked else None
        return base, result, {"turn": turn, "merge": merge, "intent": target, "rejections": rejections,
                              "ready_to_confirm": ready_to_confirm, "next_bot_text": next_bot_text,
                              "tasks": _tasks(base, turn.tasks)}


# ---------------------------------------------------------------- helpers
def _remember_district(base, live, updates):
    """No request yet ("hi, I'm from Galle"): keep the district in the conversation's memory (engine `shared`). The
    next request that needs a district gets it as a carried, unconfirmed value, so the bot asks before using it.
    live: the rules step's session in hybrid mode (its own memory of the message), else None. -> rejections"""
    rejections = []
    if live is not None:
        base.shared = dict(live.shared)
    if not isinstance(updates, dict):
        return [Rejection("slot_updates", updates, "not_an_object")] if updates else []
    for slot, value in updates.items():
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        if slot != "district":
            rejections.append(Rejection(slot, value, "no_intent"))
            continue
        try:
            district, _ = canonical_value("district", value)
        except Rejected as e:
            rejections.append(Rejection(slot, value, str(e)))
            continue
        if district != UNKNOWN_VALUE:
            base.shared["district"] = district
            base.shared.pop("town", None)
    return rejections


def _snapshot(session):
    """A deep copy of an engine Session that shares the engine (models) instead of copying it."""
    return copy.deepcopy(session, {id(session.e): session.e})


def _sync_tasks(session, llm_tasks):
    """The LLM's validated tasks: a service request it lists that the engine has no open request for is added as
    pending (with any slots the engine kept for it). The engine's own open requests are never dropped, and a request
    the engine completed stays completed."""
    open_ = {session.active_intent} | {p["intent"] for p in session.pending}
    done = {c["intent"] for c in session.completed}
    for t in llm_tasks:
        if t in CORE_INTENTS and t not in open_ and t not in done:
            session.pending.append({"intent": t, "slots": dict(session.states.get(t, {})),
                                    "conditions": dict(session.conditions.get(t, {}))})
            open_.add(t)


def _tasks(session, order=()):
    """Active request first, then the open ones: those the LLM listed in its order, then the rest."""
    active = [session.active_intent] if session.active_intent else []
    pending = [p["intent"] for p in session.pending if p["intent"] != session.active_intent]
    rank = {t: i for i, t in enumerate(order)}
    return active + sorted(pending, key=lambda t: rank.get(t, len(rank)))


def _public(slots):
    """Slots as the LLM sees them: the internal town slot is left out (district carries it)."""
    return {k: v for k, v in slots.items() if k != "town"}


def _ms(t):
    return round((time.perf_counter() - t) * 1000, 1)
