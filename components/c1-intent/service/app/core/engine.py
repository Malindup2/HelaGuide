# Service copy of research/experiments/c1_engine.py. The research copy is the reference: keep the two in
# sync (change the research copy first, then copy it here). Differences, on purpose:
#   - imports the tracker from app.core.dst instead of c1_dst
#   - torch and transformers are imported when C1Engine is created, not at module import, so stub mode
#     and CI need neither (they are in the `research` extra); @torch.no_grad() became `with torch.no_grad()`
#   - no command-line entry point
"""
C1 engine: loads the trained models (language ID, entities, intent) and runs the full multi-turn pipeline:

    language tags -> intent (last 3 user messages) -> slots (hybrid extractor) -> dialogue state -> route

Reusable from scripts, notebooks and the FastAPI service.

    from app.core.engine import C1Engine
    eng = C1Engine("models/c1/run_seed1")              # folder with lid/, ner/, intent/, c1_config.json
    s = eng.new_session()
    s.step("mata ID eka nathi una")                     # first message
    s.step("Matara", bot_text="Koheda inne?")           # bot_text = the bot's last question (optional)
    # -> {"intent": "nic_replace_lost", "slots": {"district": "Matara"}, "missing_slots": ["urgency"],
    #     "route": "orchestration", "language": "mixed", ...}
"""
import json
import time
from pathlib import Path

from app.core.dst import (AFFIRM, DENY, INTENT_SLOTS, KG_SERVICE_IDS, SERVICE_KEYWORDS, SERVICE_OF_INTENT, TOWN_DISTRICT,
                         UNKNOWN_VALUE, VARIANT_KEYWORDS, DialogueStateTracker, SlotExtractor, find_district,
                         find_town, first_word, gaz_find, is_dont_know, is_greeting, is_sinhala, refers_back,
                         requested_slot, variant_cue, words_with_offsets)

ROUTES = {
    "nic_new": "orchestration", "nic_update": "orchestration", "nic_replace_lost": "orchestration",
    "passport_new": "orchestration", "passport_renew": "orchestration", "birth_cert_copy": "orchestration",
    "marriage_registration": "orchestration", "death_cert_copy": "orchestration",
    "general_question": "orchestration", "feedback_complaint": "trust_verification",
    "unsupported_service": "fallback", "out_of_scope": "none", "unknown": "none",
}
DEFAULT_WINDOW = 3          # Observation 8: window_3 matches full history with a fixed input size
MIN_CONFIDENCE = 0.5        # below this the intent is reported as "unknown"

# ---------------------------------------------------------------- intent policy (Session)
CORE_INTENTS = {"nic_new", "nic_update", "nic_replace_lost", "passport_new", "passport_renew", "birth_cert_copy",
                "marriage_registration", "death_cert_copy"}
LOCK_CONFIDENCE = 0.6           # a core intent at this confidence becomes the active intent
LOCK_CONFIDENCE_FIRST = 0.5     # ... or at this on the first turn
SWITCH_CONFIDENCE = 0.75        # leaving the active intent also needs a keyword for the new service
CURRENT_SWITCH_CONFIDENCE = 0.5 # ... or the current message alone is that service at this, with its keyword
SHARED_SLOTS = ("district",)    # the only slot carried to a new request, and only as an assumption to confirm

# ---------------------------------------------------------------- bot replies (mixed = Singlish)
# Slot questions are worded so that dst.requested_slot() recognises them when they come back as bot_text.
ASK = {
    "applicant_for": {"mixed": "Meka kaageda?", "en": "Who is it for?", "si": "මේ කාගේද?"},
    "district": {"mixed": "Koheda inne?", "en": "Which district are you in?", "si": "කොහෙද ඉන්නේ?"},
    "date_of_birth": {"mixed": "Upan dinaya kawadada?", "en": "What is the date of birth?", "si": "උපන් දිනය කවදද?"},
    "change_field": {"mixed": "Monawada wenas karanna one? Nama, lipinaya, photo eka?",
                     "en": "What do you want to change: name, address or photo?",
                     "si": "මොනවද වෙනස් කරන්න ඕනේ? නම, ලිපිනය, ඡායාරූපය?"},
    "new_value": {"mixed": "Aluth wisthare mokakda?", "en": "What is the new name or address?",
                  "si": "අලුත් විස්තරය මොකක්ද?"},
    "urgency": {"mixed": "Ikmanata one da?", "en": "Do you need it urgently?", "si": "ඉක්මනට ඕනෙද?"},
    "service_type": {"mixed": "Normal da urgent da?", "en": "Normal or urgent service?", "si": "සාමාන්‍ය ද හදිසි ද?"},
    "travel_date": {"mixed": "Kawadada travel karanne?", "en": "When are you travelling?", "si": "කවදද ගමන් යන්නේ?"},
    "purpose": {"mixed": "Mokatada one?", "en": "What is the purpose?", "si": "මොකටද ඕනේ?"},
    "date": {"mixed": "Kawadada?", "en": "What is the date?", "si": "කවදද?"},
    "service_mentioned": {"mixed": "Mona service eka gandada?", "en": "Which service is this about?",
                          "si": "මොන සේවාව ගැනද?"},
    "issue": {"mixed": "Mokakda una prashne?", "en": "What went wrong?", "si": "මොකක්ද වුණු ප්‍රශ්නය?"},
}
REPLIES = {
    "clarify": {"mixed": "Oyata one NIC ekada, passport ekada, certificate ekakda?",
                "en": "Do you need help with an NIC, a passport or a certificate?",
                "si": "ඔබට ඕනේ හැඳුනුම්පතද, ගමන් බලපත්‍රයද, සහතිකයක්ද?"},
    "complaint": {"mixed": "Samawenna, eka check karala balannam.", "en": "Sorry about that, I'll check it.",
                  "si": "සමාවෙන්න, ඒ ගැන සොයා බලන්නම්."},
    "info": {"mixed": "Hari, {service} gana wisthara pennannam.", "en": "Sure, here is what you need to know about {service}.",
             "si": "හරි, {service} ගැන විස්තර පෙන්වන්නම්."},
    "unsupported": {"mixed": "Samawenna, {service} gana danata udaw karanna be. NIC, passport, certificate gana nam puluwan.",
                    "en": "Sorry, I can't help with {service} yet. I can help with NIC, passport and certificates.",
                    "si": "සමාවෙන්න, {service} ගැන තවම උදව් කරන්න බැහැ. හැඳුනුම්පත, ගමන් බලපත්‍ර, සහතික ගැන පුළුවන්."},
    "that_service": {"mixed": "eka", "en": "that", "si": "ඒ"},
    "out_of_scope": {"mixed": "Mata udaw karanna puluwan NIC, passport, certificate wage rajaye wada walata witharai.",
                     "en": "I can only help with government services like NIC, passport and certificates.",
                     "si": "මට උදව් කරන්න පුළුවන් හැඳුනුම්පත, ගමන් බලපත්‍ර, සහතික වගේ රජයේ කටයුතු වලට විතරයි."},
    "greeting": {"mixed": "Ayubowan! Mata kohomada udaw karanna puluwan? NIC, passport, certificate gana ahanna.",
                 "en": "Hello! How can I help you? I can help with NIC, passport and certificates.",
                 "si": "ආයුබෝවන්! මට ඔබට කොහොමද උදව් කරන්න පුළුවන්? හැඳුනුම්පත, ගමන් බලපත්‍ර, සහතික ගැන අහන්න."},
    "greeting_again": {"mixed": "Ayubowan!", "en": "Hello!", "si": "ආයුබෝවන්!"},
    # a district carried over from the previous request; worded so dst.bot_proposed_district() reads "ow"
    "confirm_assumed": {"mixed": "Thama {value} neda?", "en": "Still in {value}, right?", "si": "තවමත් {value} නේද?"},
    "offer_pending": {"mixed": "{service} eka gana ithuru tika dan ahannada?",
                      "en": "Shall we finish the {service} request now?",
                      "si": "{service} ගැන ඉතුරු ටික දැන් අහන්නද?"},
    "fallback": {"mixed": "Samawenna, mata therune na. Aye kiyanna puluwanda?",
                 "en": "Sorry, I didn't catch that. Could you say it again?",
                 "si": "සමාවෙන්න, මට තේරුණේ නැහැ. ආයෙත් කියන්න පුළුවන්ද?"},
}
# "which one?" when the service is named without a variant (VARIANT_KEYWORDS); the answer's cue picks it
VARIANT_QUESTIONS = {
    "svc:nic": {"mixed": "Aluth NIC ekak da, wenas karanna da, nathi una ekak da?",
                "en": "Is it a new NIC, a change to your NIC, or a lost NIC?",
                "si": "අලුත් හැඳුනුම්පතක්ද, වෙනස් කිරීමක්ද, නැති වුණු එකක්ද?"},
    "svc:passport": {"mixed": "Aluth passport ekak da, renew karanna da?",
                     "en": "Is it a new passport or a renewal?",
                     "si": "අලුත් ගමන් බලපත්‍රයක්ද, අලුත් කිරීමක්ද?"},
}
SERVICE_NAMES = {   # (mixed/en, si)
    "nic_new": ("new NIC", "අලුත් හැඳුනුම්පතක්"), "nic_update": ("NIC update", "හැඳුනුම්පත යාවත්කාලීන කිරීම"),
    "nic_replace_lost": ("replacement NIC", "නැතිවූ හැඳුනුම්පත වෙනුවට අලුත් එකක්"),
    "passport_new": ("new passport", "අලුත් ගමන් බලපත්‍රයක්"), "passport_renew": ("passport renewal", "ගමන් බලපත්‍රය අලුත් කිරීම"),
    "birth_cert_copy": ("birth certificate copy", "උප්පැන්න සහතිකයේ පිටපතක්"),
    "marriage_registration": ("marriage registration", "විවාහ ලියාපදිංචිය"),
    "death_cert_copy": ("death certificate copy", "මරණ සහතිකයේ පිටපතක්"),
}
APPLICANT_WORDS = {
    "self": {"mixed": "oyata", "en": "for you", "si": "ඔබට"},
    "child": {"mixed": "daruwata", "en": "for your child", "si": "දරුවාට"},
    "parent": {"mixed": "ammata/thaththata", "en": "for your parent", "si": "දෙමාපියන්ට"},
    "spouse": {"mixed": "birindata/mahaththayata", "en": "for your spouse", "si": "කලත්‍රයාට"},
    "other": {"mixed": "wena kenekta", "en": "for someone else", "si": "වෙන කෙනෙකුට"},
}
CONFIRM_LABELS = [   # slot -> label before its value in the confirmation
    ("district", {"mixed": "", "en": "in", "si": ""}),
    ("travel_date", {"mixed": "travel", "en": "travelling", "si": "ගමන"}),
    ("date_of_birth", {"mixed": "born", "en": "born", "si": "උපන්"}),
    ("date", {"mixed": "", "en": "on", "si": ""}),
    ("change_field", {"mixed": "change", "en": "change", "si": "වෙනස් කරන්නේ"}),
    ("new_value", {"mixed": "to", "en": "to", "si": "→"}),
    ("purpose", {"mixed": "for", "en": "for", "si": "අරමුණ"}),
]


class C1Engine:
    def __init__(self, model_dir, device=None, window=None, min_confidence=MIN_CONFIDENCE, use_ner=False,
                 fallback=None):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoModelForTokenClassification, AutoTokenizer

        self.torch = torch
        self.dir = Path(model_dir)
        self.cfg = json.loads((self.dir / "c1_config.json").read_text(encoding="utf-8"))
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.tok = AutoTokenizer.from_pretrained(self.dir / "lid")
        self.tok_int = AutoTokenizer.from_pretrained(self.dir / "intent")
        self.tok_int.truncation_side = "left"     # never cut off the newest message
        # saved in fp16, run in fp32 (works on CPU)
        self.lid = AutoModelForTokenClassification.from_pretrained(self.dir / "lid").float().to(self.device).eval()
        self.ner = AutoModelForTokenClassification.from_pretrained(self.dir / "ner").float().to(self.device).eval()
        self.intent = AutoModelForSequenceClassification.from_pretrained(self.dir / "intent").float().to(self.device).eval()
        self.max_len = self.cfg.get("max_len", 128)
        self.sep = self.cfg.get("history_separator", " </s> ")
        self.window = window if window is not None else self.cfg.get("intent_window", DEFAULT_WINDOW)
        self.min_confidence = min_confidence
        self.use_ner = use_ner                    # XLM-R entities as a fallback for free-text slots
        self.fallback = fallback                  # optional callable(text) -> intent or None, used below min_confidence
        self.known_intents = set(self.intent.config.id2label.values())

    # ---------------------------------------------------------------- single-message helpers
    def _word_labels(self, model, words):
        if not words:
            return []
        enc = self.tok(words, is_split_into_words=True, truncation=True, max_length=self.max_len, return_tensors="pt")
        with self.torch.no_grad():
            logits = model(input_ids=enc["input_ids"].to(self.device),
                           attention_mask=enc["attention_mask"].to(self.device)).logits[0]
        best = logits.argmax(-1).tolist()
        out, prev = {}, None
        for k, w in enumerate(enc.word_ids(0)):
            if w is not None and w != prev:
                out[w] = model.config.id2label[best[k]]
            prev = w
        return [out.get(i, "O") for i in range(len(words))]

    def tag_languages(self, text):
        spans = list(words_with_offsets(text))
        tags = self._word_labels(self.lid, [w for w, _, _ in spans])
        return [(w, t) for (w, _, _), t in zip(spans, tags)]

    def extract_entities(self, text):
        spans = list(words_with_offsets(text))
        tags = self._word_labels(self.ner, [w for w, _, _ in spans])
        ents, cur = [], None
        for (w, s, e), t in zip(spans, tags):
            if t.startswith("B-") or (t.startswith("I-") and (cur is None or cur["type"] != t[2:])):
                cur = {"type": t[2:], "start": s, "end": e}
                ents.append(cur)
            elif t.startswith("I-") and cur is not None:
                cur["end"] = e
            else:
                cur = None
        for x in ents:
            x["text"] = text[x["start"]:x["end"]]
        return ents

    def classify_intent(self, user_turns):
        """user_turns: the citizen's messages so far, oldest first. Uses the last `window` of them."""
        torch = self.torch
        ctx = user_turns if not self.window else user_turns[-self.window:]
        enc = self.tok_int(self.sep.join(ctx), truncation=True, max_length=self.max_len, return_tensors="pt")
        with torch.no_grad():
            probs = torch.softmax(self.intent(input_ids=enc["input_ids"].to(self.device),
                                              attention_mask=enc["attention_mask"].to(self.device)).logits[0], -1)
        i = int(probs.argmax())
        return self.intent.config.id2label[i], round(float(probs[i]), 4)

    def classify_current(self, text):
        """The current message alone, no history (used to spot a new service or a complaint)."""
        return self.classify_intent([text])

    @staticmethod
    def language_of(tags):
        present = {t for _, t in tags if t in ("SI", "EN")}
        if present == {"SI", "EN"} or any(t == "MIXED" for _, t in tags):
            return "mixed"
        return {"SI": "si", "EN": "en"}.get(next(iter(present), ""), "mixed" if not present else "en")

    def new_session(self):
        return Session(self)

    def analyse(self, user_turns):
        """Backwards-compatible: analyse the last message given all earlier user messages (no bot turns)."""
        s = self.new_session()
        out = None
        for t in user_turns:
            out = s.step(t)
        return out


class Session:
    """
    One conversation: keeps the user's messages and the dialogue state between turns.

    Intent policy (no retraining, on top of the classifier):
    - active_intent: set when a core intent is predicted at LOCK_CONFIDENCE (LOCK_CONFIDENCE_FIRST on the first
      turn). Later turns keep it unless the citizen asks for another service:
        1. the message names a different service (SERVICE_KEYWORDS) and the current message alone, without
           history, is classified as that service at CURRENT_SWITCH_CONFIDENCE (any turn), or
        2. the usual (windowed) prediction is another core intent at SWITCH_CONFIDENCE and the message names
           it, unless the message answers a pending slot question.
    - Several requests per conversation: on a switch the old request goes to completed_requests when all its
      slots are filled, else to pending_requests; once the new one is ready the bot offers to finish the
      pending one, and "ow" resumes it.
    - feedback_complaint (windowed or current-message prediction) is routed to trust_verification but does not
      replace active_intent.
    - Slot state is kept per intent. A new request starts an empty slot frame: only the conversation's district is
      carried, marked assumed, and the bot asks "Thama Galle neda?" before treating it as known. Switching back
      to an earlier request restores its own slots. Core requests without a district slot (passport) keep the
      conversation's district as context.
    - Towns fill district (TOWNS), and "danne na" to a slot question fills that slot with "unknown".
    - Greetings get a greeting and change nothing. Every turn gets a bot reply.
    - A new request that names a service with several variants but no variant cue ("i need a NIC") keeps the
      service, marks the variant pending and asks "Aluth NIC ekak da, wenas karanna da, nathi una ekak da?". The
      next answer picks it by its cue ("aluth", "nathi una", "renew"), or by a slot only one variant has
      ("nangita" -> applicant_for -> passport_new). Until then the request is not ready.
    - Condition facts (applicant_age, applicant_minor) are kept per request like slots and returned as
      `conditions`; they are never asked for and never change routing.
    - state_version goes up whenever the active request's intent, slots, conditions or pending variant change, so
      a caller knows when to ask C2 again.
    """

    def __init__(self, engine):
        self.e = engine
        self.turns = []             # every user message (turn_id counts these)
        self.history = []           # what the intent model reads: greetings are left out
        ner = engine.extract_entities if engine.use_ner else None
        self.tracker = DialogueStateTracker(SlotExtractor(ner=ner))
        self.active_intent = None
        self.states = {}            # intent -> its slots, so switching back restores them
        self.shared = {}            # latest district / town heard in any turn
        self.assumed = {}           # intent -> carried slots the citizen has not confirmed yet
        self.confirming = None      # slot the last reply asked the citizen to confirm
        self.completed = []         # finished requests, oldest first: {"intent", "slots"}
        self.pending = []           # requests left unfinished by a switch, oldest first
        self.offered = None         # pending intent the last reply offered to resume
        self.reply_lang = None
        self.conditions = {}        # intent -> its condition facts (applicant_age, applicant_minor)
        self.variant_pending = {}   # KG service -> the provisional intent of a request whose variant is not known
        self.state_version = 0
        self._signature = None      # what state_version was last counted for

    def step(self, text, bot_text=None):
        t0 = time.perf_counter()
        self.turns.append(text)
        tags = self.e.tag_languages(text)
        language = self.e.language_of(tags)
        if not self.history or len(tags) >= 3 or self.reply_lang is None:
            self.reply_lang = reply_language(tags, language)    # short answers ("normal", "galle") keep it
        if is_greeting(text):
            return self._result(text, t0, tags, language, "unknown", "none", 0.0, "greeting", self._greeting())
        first = not self.history
        self.history.append(text)
        intent, conf = self.e.classify_intent(self.history)
        current = (intent, conf) if first else self.e.classify_current(text)
        before = self.active_intent
        intent_used, source = self._choose_intent(text, intent, conf, current, bot_text, first)
        intent_used, source = self._choose_variant(text, bot_text, intent, intent_used, source, before)
        frame = self._load_state(intent_used, text)
        self.tracker.update(text, intent_used, bot_text, frame=frame)
        words = list(words_with_offsets(text))
        self._fill_town(words, intent_used)
        self._confirm_assumed(words, intent_used)
        self._dont_know(text, bot_text, intent_used)
        self._remember_shared(words, intent_used)
        self._add_context(intent_used)
        self.states[intent_used] = dict(self.tracker.slots)
        self.assumed[intent_used] = set(self.tracker.assumed)
        self.conditions[intent_used] = dict(self.tracker.conditions)
        self._count_version()
        return self._result(text, t0, tags, language, intent, intent_used, conf, source,
                            self._reply(intent_used, first, self.tracker.slots))

    def _result(self, text, t0, tags, language, model_intent, intent_used, conf, source, reply):
        active = self.active_intent
        slots = dict(self.tracker.slots) if intent_used != "none" else dict(self.states.get(active, {}))
        conditions = dict(self.tracker.conditions) if intent_used != "none" else dict(self.conditions.get(active, {}))
        shown = intent_used if intent_used != "none" else active
        missing = self._missing(shown)
        assumed = sorted(self.assumed.get(shown, set()) & set(INTENT_SLOTS.get(shown, [])))
        variant_pending = shown in self.variant_pending.values()
        return {
            "turn_id": len(self.turns) - 1,
            "state_version": self.state_version,
            "text": text,
            "intent": "unknown" if intent_used == "none" else intent_used,
            "intent_model_output": model_intent, "intent_confidence": conf, "intent_source": source,
            "active_intent": active,
            "active_slots": dict(self.states.get(active, {})) if active else slots,
            "intent_locked": active is not None and intent_used == active
                             and source in ("active_intent", "previous_topic"),
            "ready": active is not None and intent_used == active and not missing and not assumed
                     and not variant_pending,
            "assumed_slots": assumed,
            "variant_pending": variant_pending,
            "reply": reply,
            "completed_requests": [self._summary(r) for r in self.completed],
            "pending_requests": [self._summary(r) for r in self.pending],
            "route": ROUTES.get(intent_used, "none"),
            "slots": slots,
            "conditions": conditions,
            "missing_slots": missing,
            "slot_spans": {k: v for k, v in self.tracker.spans.items() if v.get("start") is not None}
                          if intent_used != "none" else {},
            "language": language,
            "language_tags": [{"word": w, "tag": t} for w, t in tags],
            "code_switched": {t for _, t in tags if t in ("SI", "EN")} == {"SI", "EN"},
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        }

    def _summary(self, req):
        return {"intent": req["intent"], "service_id": KG_SERVICE_IDS.get(req["intent"]), "slots": dict(req["slots"]),
                "conditions": dict(req.get("conditions", {})),
                "variant_pending": req["intent"] in self.variant_pending.values()}

    def _missing(self, intent):
        slots = self.states.get(intent, {}) if intent != self.tracker.intent else self.tracker.slots
        return [s for s in INTENT_SLOTS.get(intent, []) if s not in slots]

    # ---------------------------------------------------------------- intent policy
    def _choose_intent(self, text, intent, conf, current, bot_text, first):
        """-> (intent used for this turn, source). Updates active_intent and the request lists."""
        cur_intent, cur_conf = current
        active = self.active_intent
        offered, self.offered = self.offered, None
        asked = requested_slot(bot_text, active) if active else None
        slot_answer = active is not None and asked in INTENT_SLOTS[active] and asked not in self.states.get(active, {})
        # a complaint needs SWITCH_CONFIDENCE only when the message really answers the pending question
        answered = slot_answer and asked in self.tracker.x.extract(text, active, bot_text, self.states.get(active, {}))
        complaint_min = SWITCH_CONFIDENCE if answered else self.e.min_confidence
        complaint = (intent == "feedback_complaint" and conf >= complaint_min) or \
                    (cur_intent == "feedback_complaint" and cur_conf >= complaint_min)

        if active is None:
            if intent in CORE_INTENTS and conf >= (LOCK_CONFIDENCE_FIRST if first else LOCK_CONFIDENCE):
                self._switch_to(intent)
                return intent, "model"
            if complaint:
                return "feedback_complaint", "model"
            return self._unlocked(text, intent, conf)

        # 1. the message asks for another service, judged on the message alone
        named = named_services(text) - {KG_SERVICE_IDS[active]}
        if cur_intent in CORE_INTENTS and KG_SERVICE_IDS.get(cur_intent) in named \
                and cur_conf >= CURRENT_SWITCH_CONFIDENCE:
            self._switch_to(cur_intent)
            return cur_intent, "current_message_switch"
        # "ow" to "shall we finish the NIC request now?"
        if offered and first_word(list(words_with_offsets(text))) in AFFIRM:
            self._switch_to(offered)
            return offered, "pending_resume"
        if complaint:
            return "feedback_complaint", "model"    # to C3; active_intent stays and the conversation resumes
        if intent == active and conf >= self.e.min_confidence:
            return active, "model"
        # 2. the windowed prediction, with a keyword for the new service, and not on a slot answer
        if not slot_answer and intent in CORE_INTENTS and conf >= SWITCH_CONFIDENCE and self._names_service(text, intent):
            self._switch_to(intent)
            return intent, "model"
        return active, "active_intent" if conf >= self.e.min_confidence else "previous_topic"

    def _switch_to(self, new):
        """Make `new` the active request; file the old one as completed (all slots filled) or pending."""
        old = self.active_intent
        if old and old != new:
            req = {"intent": old, "slots": dict(self.states.get(old, {})), "conditions": dict(self.conditions.get(old, {}))}
            self.pending = [p for p in self.pending if p["intent"] != old]
            (self.pending if self._missing(old) else self.completed).append(req)
        # going back to a request reopens it
        self.pending = [p for p in self.pending if p["intent"] != new]
        self.completed = [c for c in self.completed if c["intent"] != new]
        self.active_intent = new

    def _choose_variant(self, text, bot_text, model_intent, intent_used, source, before):
        """Variant policy, after _choose_intent. -> (intent used for this turn, source).
        - A request whose variant is pending: a cue in the message, or a slot only one variant has, picks it; a
          prediction of another variant of the same service without either does not change the request.
        - A new request that names a service with variants but no cue gets its variant marked pending, also on an
          unsure turn with no active request (the model's variant, else the last listed one, is kept for now)."""
        svc = KG_SERVICE_IDS.get(intent_used)
        provisional = self.variant_pending.get(svc)
        if provisional:
            chosen = variant_cue(text, svc) or self._variant_from_slots(text, svc, bot_text)
            self._rename_request(provisional, chosen or provisional)
            if chosen:
                del self.variant_pending[svc]
                return chosen, "variant_answer"
            return provisional, source if intent_used == provisional else "active_intent"
        if svc in VARIANT_KEYWORDS:
            new_request = intent_used == self.active_intent != before
            if new_request and self._bare_mention(text, svc):
                self.variant_pending[svc] = intent_used
            return intent_used, source
        if self.active_intent is None and (intent_used == "unknown" or source == "previous_topic"):
            named = named_services(text) & set(VARIANT_KEYWORDS)
            if len(named) == 1 and self._bare_mention(text, *named):
                svc = named.pop()
                variants = [i for i, _ in VARIANT_KEYWORDS[svc]]
                provisional = model_intent if model_intent in variants else variants[-1]
                self._switch_to(provisional)
                self.variant_pending[svc] = provisional
                return provisional, "service_keyword"
        return intent_used, source

    def _bare_mention(self, text, svc):
        """The message names `svc`, has no variant cue, and the conversation has no request for it yet."""
        return svc in named_services(text) and not variant_cue(text, svc) \
            and not any(KG_SERVICE_IDS.get(i) == svc for i in self.states)

    def _variant_from_slots(self, text, svc, bot_text):
        """The one variant of `svc` that has a slot the message fills and the other variants do not have."""
        variants = [i for i, _ in VARIANT_KEYWORDS[svc]]
        found = set()
        for v in variants:
            own = set(INTENT_SLOTS[v]).difference(*(INTENT_SLOTS[o] for o in variants if o != v))
            if own & set(self.tracker.x.extract(text, v, bot_text, {})):
                found.add(v)
        return found.pop() if len(found) == 1 else None

    def _rename_request(self, old, new):
        """Move the request filed under `old` (a provisional variant) to `new` and make it active."""
        self.pending = [p for p in self.pending if p["intent"] not in (old, new)]
        self.completed = [c for c in self.completed if c["intent"] not in (old, new)]
        self.active_intent = new
        if old == new:
            return
        keep = set(INTENT_SLOTS[new]) | {"town"}
        self.states[new] = {k: v for k, v in self.states.pop(old, {}).items() if k in keep}
        self.assumed[new] = self.assumed.pop(old, set()) & set(self.states[new])
        self.conditions[new] = self.conditions.pop(old, {})
        if self.tracker.intent == old:
            self.tracker.intent, self.tracker.slots = new, dict(self.states[new])
            self.tracker.assumed = set(self.assumed[new])

    def _count_version(self):
        """state_version + 1 when the active request (intent, slots, conditions, pending variant) changed."""
        a = self.active_intent
        signature = (a, sorted(self.states.get(a, {}).items()), sorted(self.conditions.get(a, {}).items()),
                     a in self.variant_pending.values()) if a else None
        if signature != self._signature:
            self._signature = signature
            self.state_version += 1

    def _unlocked(self, text, intent, conf):
        if conf >= self.e.min_confidence:
            return intent, "model"
        fallback = self.e.fallback(text) if self.e.fallback else None
        if fallback:
            return fallback, "keyword_fallback"
        if self.tracker.intent:
            return self.tracker.intent, "previous_topic"        # unsure: keep the current topic
        return "unknown", "unknown"

    @staticmethod
    def _names_service(text, intent):
        return KG_SERVICE_IDS.get(intent) in named_services(text)

    # ---------------------------------------------------------------- slots
    def _load_state(self, intent, text):
        """Before the tracker runs: the slot frame this intent starts from, or None to carry on as before.
        A request seen before gets its own slots back. A new one starts empty except for the conversation's
        district, which is marked assumed, and applicant_for when the message points back to that person
        ("eyata ID eka ganna"); applicant_for is never guessed."""
        if intent == self.tracker.intent:
            return None
        if intent in self.states:
            self.tracker.assumed = set(self.assumed.get(intent, set()))
            self.tracker.conditions = dict(self.conditions.get(intent, {}))
            return dict(self.states[intent])
        frame = {}
        if "district" in INTENT_SLOTS.get(intent, []) and self.shared.get("district"):
            frame["district"] = self.shared["district"]
            if self.shared.get("town") and TOWN_DISTRICT.get(self.shared["town"]) == frame["district"]:
                frame["town"] = self.shared["town"]
        person = self.tracker.slots.get("applicant_for")
        back = refers_back(text)
        if "applicant_for" in INTENT_SLOTS.get(intent, []) and person not in (None, UNKNOWN_VALUE) and back:
            frame["applicant_for"] = person
        self.tracker.assumed = set(frame) & set(SHARED_SLOTS)
        self.tracker.conditions = dict(self.tracker.conditions) if back else {}     # same person, same facts
        return frame

    def _confirm_assumed(self, words, intent):
        """Answer to "Thama Galle neda?": "ow" confirms the carried district, "na" drops it so it is asked."""
        confirming, self.confirming = self.confirming, None
        if confirming not in self.tracker.assumed or intent != self.active_intent:
            return
        fw = first_word(words)
        if fw in AFFIRM:
            self.tracker.assumed.discard(confirming)
        elif fw in DENY and confirming not in self.tracker.spans:
            self.tracker.slots.pop(confirming, None)
            if confirming == "district":
                self.tracker.slots.pop("town", None)
            self.tracker.assumed.discard(confirming)

    def _fill_town(self, words, intent):
        """A town fills district (and the town slot) when the tracker found no district name this turn."""
        slots = self.tracker.slots
        if slots.get("town") and TOWN_DISTRICT.get(slots["town"]) != slots.get("district"):
            del slots["town"]                       # district was corrected to another one
        hit = find_town(words)
        if not hit:
            return
        town, district = hit
        if "district" not in INTENT_SLOTS.get(intent, []):
            return
        if "district" not in self.tracker.spans or slots.get("district") == district:
            slots["district"], slots["town"] = district, town
            self.tracker.assumed.discard("district")      # said this turn, so no longer assumed

    def _dont_know(self, text, bot_text, intent):
        """'danne na' to the bot's question for a missing slot: the slot becomes 'unknown' and is not asked again."""
        if intent != self.active_intent or not is_dont_know(text):
            return
        asked = requested_slot(bot_text, intent)
        before = self.states.get(intent, {})
        if asked in INTENT_SLOTS.get(intent, []) and asked not in before:
            for k in list(self.tracker.spans):      # "i dont know" must not fill applicant_for = self
                if k not in before:
                    self.tracker.slots.pop(k, None)
            self.tracker.slots[asked] = UNKNOWN_VALUE

    def _remember_shared(self, words, intent):
        for k in SHARED_SLOTS + ("town",):
            if self.tracker.slots.get(k) not in (None, UNKNOWN_VALUE):
                self.shared[k] = self.tracker.slots[k]
        if "district" not in INTENT_SLOTS.get(intent, []):
            hit = find_district(words)
            town = find_town(words)
            if hit:
                self.shared["district"] = hit[2]
                self.shared.pop("town", None)
            elif town:
                self.shared["town"], self.shared["district"] = town

    def _add_context(self, intent):
        """Core requests without a district slot (passport) still keep the district heard in the conversation:
        not asked for and not needed for `ready`, but carried and sent in the contract (which office)."""
        if intent in CORE_INTENTS and "district" not in INTENT_SLOTS[intent] and self.shared.get("district"):
            self.tracker.slots["district"] = self.shared["district"]
            if self.shared.get("town") and TOWN_DISTRICT.get(self.shared["town"]) == self.shared["district"]:
                self.tracker.slots["town"] = self.shared["town"]
            else:
                self.tracker.slots.pop("town", None)

    # ---------------------------------------------------------------- bot reply
    def _greeting(self):
        lang = self.reply_lang
        if self.active_intent:
            return REPLIES["greeting_again"][lang] + " " + self._next_step(self.active_intent, lang)
        return REPLIES["greeting"][lang]

    def _reply(self, intent, first, slots):
        lang = self.reply_lang
        active = self.active_intent
        if intent == "feedback_complaint":
            return REPLIES["complaint"][lang] + (" " + self._next_step(active, lang) if active else "")
        if active and intent == active:
            return self._next_step(active, lang)
        if first and (intent == "unknown" or intent in CORE_INTENTS):
            return REPLIES["clarify"][lang]
        if intent in CORE_INTENTS:
            return self._next_step(intent, lang)
        service = slots.get("service_mentioned")
        if intent == "general_question":
            return REPLIES["info"][lang].format(service=service) if service else ASK["service_mentioned"][lang]
        if intent == "unsupported_service":
            return REPLIES["unsupported"][lang].format(service=service or REPLIES["that_service"][lang])
        if intent == "out_of_scope":
            return REPLIES["out_of_scope"][lang]
        return REPLIES["fallback"][lang]

    def _next_step(self, intent, lang):
        """The next slot to ask for, in schema order; a carried (assumed) slot is confirmed at its turn. A pending
        variant is asked first."""
        for svc, provisional in self.variant_pending.items():
            if provisional == intent:
                return VARIANT_QUESTIONS[svc][lang]
        slots = self.states.get(intent, {})
        assumed = self.assumed.get(intent, set())
        for s in INTENT_SLOTS.get(intent, []):
            if s not in slots:
                return ASK[s][lang]
            if s in assumed:
                if intent == self.active_intent:
                    self.confirming = s
                return REPLIES["confirm_assumed"][lang].format(value=slots[s])
        reply = confirmation(intent, slots, lang)
        if intent == self.active_intent and self.pending:
            self.offered = self.pending[-1]["intent"]
            reply += " " + REPLIES["offer_pending"][lang].format(service=SERVICE_OF_INTENT[self.offered])
        return reply


def reply_language(tags, language):
    """Script of the bot's reply: "si" (Sinhala script) when most words are in Sinhala script, "en" for English,
    else "mixed" (Singlish). Not the same as `language`: romanized Sinhala is tagged SI by the model."""
    sinhala = sum(is_sinhala(w) for w, _ in tags)
    if tags and sinhala * 2 >= len(tags):
        return "si"
    return "en" if language == "en" else "mixed"


def named_services(text):
    """KG service IDs whose keywords appear in the message."""
    words = list(words_with_offsets(text))
    return {svc for svc, forms in SERVICE_KEYWORDS.items() if gaz_find(text, [(svc, forms)], words)}


def confirmation(intent, slots, lang):
    """'Hari — normal new passport, oyata, travel next year. Documents tika pennannam.'"""
    known = {k: v for k, v in slots.items() if v != UNKNOWN_VALUE}
    name = SERVICE_NAMES[intent][1 if lang == "si" else 0]
    kind = known.get("service_type") or known.get("urgency")
    head = f"{kind} {name}" if kind and lang != "si" else name
    parts = []
    if known.get("applicant_for"):
        parts.append(APPLICANT_WORDS[known["applicant_for"]][lang])
    for slot, label in CONFIRM_LABELS:
        if known.get(slot):
            value = known[slot]
            if slot == "district" and known.get("town"):
                value = f"{known['town']} ({value})"
            prefix = label[lang]
            if prefix and value.lower().startswith(prefix.lower() + " "):
                prefix = ""                         # "for school admission", not "for for school admission"
            parts.append(f"{prefix} {value}".strip())
    if lang == "si" and kind:
        parts.insert(0, kind)
    body = ", ".join([head] + parts)
    return {"mixed": f"Hari — {body}. Documents tika pennannam.",
            "en": f"Okay — {body}. I'll show you the documents you need.",
            "si": f"හරි — {body}. අවශ්‍ය ලේඛන පෙන්වන්නම්."}[lang]
