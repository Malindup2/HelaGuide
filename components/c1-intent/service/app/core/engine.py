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

from app.core.dst import DialogueStateTracker, SlotExtractor, words_with_offsets

ROUTES = {
    "nic_new": "orchestration", "nic_update": "orchestration", "nic_replace_lost": "orchestration",
    "passport_new": "orchestration", "passport_renew": "orchestration", "birth_cert_copy": "orchestration",
    "marriage_registration": "orchestration", "death_cert_copy": "orchestration",
    "general_question": "orchestration", "feedback_complaint": "trust_verification",
    "unsupported_service": "fallback", "out_of_scope": "none", "unknown": "none",
}
DEFAULT_WINDOW = 3          # Observation 8: window_3 matches full history with a fixed input size
MIN_CONFIDENCE = 0.5        # below this the intent is reported as "unknown"


class C1Engine:
    def __init__(self, model_dir, device=None, window=None, min_confidence=MIN_CONFIDENCE, use_ner=False):
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
    """One conversation: keeps the user's messages and the dialogue state between turns."""

    def __init__(self, engine):
        self.e = engine
        self.turns = []
        ner = engine.extract_entities if engine.use_ner else None
        self.tracker = DialogueStateTracker(SlotExtractor(ner=ner))

    def step(self, text, bot_text=None):
        t0 = time.perf_counter()
        self.turns.append(text)
        tags = self.e.tag_languages(text)
        intent, conf = self.e.classify_intent(self.turns)
        if conf < self.e.min_confidence:
            intent_used = self.tracker.intent or "unknown"      # unsure: keep the current topic
        else:
            intent_used = intent
        state = self.tracker.update(text, intent_used, bot_text)
        return {
            "turn_id": len(self.turns) - 1,
            "text": text,
            "intent": intent_used, "intent_model_output": intent, "intent_confidence": conf,
            "route": ROUTES.get(intent_used, "none"),
            "slots": state["slots"],
            "missing_slots": self.tracker.missing_slots(),
            "slot_spans": {k: v for k, v in self.tracker.spans.items() if v.get("start") is not None},
            "language": self.e.language_of(tags),
            "language_tags": [{"word": w, "tag": t} for w, t in tags],
            "code_switched": {t for _, t in tags if t in ("SI", "EN")} == {"SI", "EN"},
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        }
