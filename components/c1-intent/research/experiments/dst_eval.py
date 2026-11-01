"""
Evaluate multi-turn slot tracking (sub-objective 2): joint goal accuracy (JGA), per-slot scores and
entity span F1, for the hybrid extractor + dialogue state tracker in c1_dst.py.

Run from research/ (CPU is fine):
    python experiments/dst_eval.py
    python experiments/dst_eval.py --xlmr-dir models/c1/run_seed1     # also XLM-R intent + NER (slower)

What it measures
  1. Dialogue state tracking on the gold dialogues (data/seed_all.json, 70 dialogues / 142 user turns):
     JGA = the intent AND every slot value are right at that turn (the standard multi-turn metric).
     Intent comes from: gold labels (oracle, isolates slot tracking), TF-IDF window_3 trained on the silver set,
     and XLM-R window_3 (if --xlmr-dir). Four tracker settings show what each part adds (ablation).
  2. The same on the synthetic dialogues (held-out for the rules: they were not used to write them).
  3. Entity span F1 on gold_tokens.jsonl and fresh_tokens.jsonl, comparable to the XLM-R NER numbers
     in Observation 7 (gold 0.528, fresh 0.394).

Writes results/dst_results.json.
"""
import argparse
import collections
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from c1_dst import (INTENT_SLOTS, DialogueStateTracker, SlotExtractor, states_match, values_match,  # noqa: E402
                    words_with_offsets)

CORE = ["birth_cert_copy", "death_cert_copy", "marriage_registration", "nic_new", "nic_replace_lost", "nic_update",
        "passport_new", "passport_renew"]
SEP = " </s> "
WINDOW = 3


def load_json(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def load_jsonl(p):
    with open(p, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def user_turns(d):
    """[(turn_index, text, gold_state, bot_text_before)]"""
    out, bot = [], None
    for i, t in enumerate(d["turns"]):
        if t.get("speaker") == "bot":
            bot = t["text"]
            continue
        out.append((i, t["text"], t.get("state", {}), bot))
    return out


def window_inputs(dialogues):
    """window_3 input for every user turn, in order."""
    xs = []
    for d in dialogues:
        texts = []
        for _, text, _, _ in user_turns(d):
            texts.append(text)
            xs.append(SEP.join(texts[-WINDOW:]))
    return xs


# ------------------------------------------------------------------ intent sources
def tfidf_intent(silver_dialogues):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline, make_union
    xs = window_inputs(silver_dialogues)
    ys = [s.get("intent") for d in silver_dialogues for _, _, s, _ in user_turns(d)]
    m = make_pipeline(make_union(TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True),
                                 TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True)),
                      LogisticRegression(max_iter=3000, C=10))
    m.fit(xs, ys)
    return lambda inputs: list(m.predict(inputs))


class XLMR:
    """Loads the intent and NER models saved by c1_xlmr_train.ipynb (CPU)."""

    def __init__(self, model_dir):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoModelForTokenClassification, AutoTokenizer
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(os.path.join(model_dir, "intent"))
        self.tok.truncation_side = "left"
        self.intent = AutoModelForSequenceClassification.from_pretrained(os.path.join(model_dir, "intent")).float().eval()
        self.ner_model = AutoModelForTokenClassification.from_pretrained(os.path.join(model_dir, "ner")).float().eval()

    def predict_intent(self, inputs):
        out = []
        with self.torch.no_grad():
            for i in range(0, len(inputs), 16):
                enc = self.tok(inputs[i:i + 16], truncation=True, max_length=128, padding=True, return_tensors="pt")
                ids = self.intent(**enc).logits.argmax(-1).tolist()
                out += [self.intent.config.id2label[j] for j in ids]
        return out

    def ner(self, text):
        words = list(words_with_offsets(text))
        if not words:
            return []
        with self.torch.no_grad():
            enc = self.tok([w for w, _, _ in words], is_split_into_words=True, truncation=True, max_length=128,
                           return_tensors="pt")
            best = self.ner_model(**enc).logits[0].argmax(-1).tolist()
        tags, prev = {}, None
        for k, w in enumerate(enc.word_ids(0)):
            if w is not None and w != prev:
                tags[w] = self.ner_model.config.id2label[best[k]]
            prev = w
        ents, cur = [], None
        for i, (w, s, e) in enumerate(words):
            t = tags.get(i, "O")
            if t.startswith("B-") or (t.startswith("I-") and (cur is None or cur["type"] != t[2:])):
                cur = {"type": t[2:], "start": s, "end": e}
                ents.append(cur)
            elif t.startswith("I-") and cur:
                cur["end"] = e
            else:
                cur = None
        for x in ents:
            x["text"] = text[x["start"]:x["end"]]
        return ents


class NerOnlyExtractor:
    """Baseline: slot values straight from XLM-R entity spans (no rules), filtered by the intent's slots."""

    def __init__(self, ner):
        self.ner = ner

    def extract(self, text, intent, bot_text=None, prev_state=None):
        allowed = set(INTENT_SLOTS.get(intent, []))
        return {e["type"]: {"value": e["text"], "start": e["start"], "end": e["end"]}
                for e in self.ner(text) if e["type"] in allowed}


# ------------------------------------------------------------------ evaluation
def tracker_settings(ner=None):
    s = {
        "1_no_memory": lambda: DialogueStateTracker(SlotExtractor(use_context=False, use_negation=False),
                                                    carryover=False, switch_filter=False, corrections=False),
        "2_carryover": lambda: DialogueStateTracker(SlotExtractor(use_context=False, use_negation=False),
                                                    carryover=True, switch_filter=False, corrections=False),
        "3_+bot_question": lambda: DialogueStateTracker(SlotExtractor(use_context=True, use_negation=False),
                                                        carryover=True, switch_filter=False, corrections=False),
        "4_full": lambda: DialogueStateTracker(SlotExtractor(), carryover=True, switch_filter=True, corrections=True),
    }
    if ner:
        s["5_full+xlmr_ner"] = lambda: DialogueStateTracker(SlotExtractor(ner=ner))
        s["0_xlmr_ner_only"] = lambda: DialogueStateTracker(NerOnlyExtractor(ner), carryover=True)
    return s


def run_dst(dialogues, intents, make_tracker, relaxed=True):
    """intents: predicted intent per user turn (same order as user_turns over dialogues)."""
    per_slot = new_slot_counts()
    rows, k = [], 0
    for d in dialogues:
        trk = make_tracker()
        trk.reset()
        core_dialogue = is_core_dialogue(d)
        for pos, (ti, text, gold, bot) in enumerate(user_turns(d)):
            pred = trk.update(text, intents[k], bot)
            k += 1
            rows.append(score_turn(per_slot, f"{d['dialogue_id']}/{ti}", pos, core_dialogue, pred, gold, relaxed))
    return summarise_rows(rows, per_slot)


# ------------------------------------------------------------------ scoring (also used by dialogue_eval.py)
def new_slot_counts():
    """{slot: [true positives, false positives, false negatives]}, filled by score_turn."""
    return collections.defaultdict(lambda: [0, 0, 0])


def is_core_dialogue(d):
    """Every user turn's gold intent is a core service (the "core dialogues" subset)."""
    return all(s.get("intent") in CORE for _, _, s, _ in user_turns(d))


def score_turn(per_slot, row_id, pos, core_dialogue, pred, gold, relaxed=True):
    """One user turn: adds its slot comparison to per_slot and returns its row for summarise_rows.
    pred: {"intent", "slots"} as predicted; gold: the turn's gold state ({"intent", "slots"})."""
    gs, ps = gold.get("slots", {}) or {}, pred["slots"]
    slots_ok = states_match(ps, gs, relaxed)
    row = {"id": row_id, "pos": pos, "core": core_dialogue,
           "intent_ok": pred["intent"] == gold.get("intent"), "slots_ok": slots_ok,
           "pred": pred, "gold": {"intent": gold.get("intent"), "slots": gs}}
    for slot in set(gs) | set(ps):
        if slot in gs and slot in ps and values_match(slot, ps[slot], gs[slot], relaxed):
            per_slot[slot][0] += 1
        else:
            if slot in ps:
                per_slot[slot][1] += 1
            if slot in gs:
                per_slot[slot][2] += 1
    return row


def summarise_rows(rows, per_slot):
    """JGA, slot JGA, intent accuracy (all / core dialogues / turn 2+), per-slot and micro P/R/F1, first errors."""
    def acc(rs, key):
        return round(sum(key(r) for r in rs) / len(rs), 4) if rs else None

    def prf(tp, fp, fn):
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0,
                "support": tp + fn}

    core = [r for r in rows if r["core"]]
    later = [r for r in rows if r["pos"] > 0]
    res = {
        "turns": len(rows), "core_dialogue_turns": len(core),
        "jga": acc(rows, lambda r: r["intent_ok"] and r["slots_ok"]),
        "slot_jga": acc(rows, lambda r: r["slots_ok"]),
        "intent_acc": acc(rows, lambda r: r["intent_ok"]),
        "jga_core_dialogues": acc(core, lambda r: r["intent_ok"] and r["slots_ok"]),
        "slot_jga_core_dialogues": acc(core, lambda r: r["slots_ok"]),
        "jga_turn2plus": acc(later, lambda r: r["intent_ok"] and r["slots_ok"]),
        "per_slot": {s: prf(*v) for s, v in sorted(per_slot.items())},
        "errors": [{"id": r["id"], "pred": r["pred"], "gold": r["gold"]} for r in rows
                   if not (r["intent_ok"] and r["slots_ok"])][:60],
    }
    tot = [sum(v[i] for v in per_slot.values()) for i in range(3)]
    res["slot_micro"] = prf(*tot)
    return res


# ------------------------------------------------------------------ span-level entity F1
def spans_from_bio(tags):
    out, start, typ = set(), None, None
    for i, t in enumerate(list(tags) + ["O"]):
        if t.startswith("B-") or t == "O" or (t.startswith("I-") and t[2:] != typ):
            if typ is not None:
                out.add((start, i, typ))
            start, typ = (i, t[2:]) if t != "O" else (None, None)
    return out


def char_to_word_spans(text, spans):
    words = list(words_with_offsets(text))
    out = set()
    for typ, s, e in spans:
        if s is None:
            continue
        idx = [i for i, (_, ws, we) in enumerate(words) if ws < e and we > s]
        if idx:
            out.add((idx[0], idx[-1] + 1, typ))
    return out


def span_eval(rows, dialogues, make_extractor, intent_of_row):
    """Span F1 of the extractor on token rows (gold_tokens / fresh_tokens). Bot text comes from the dialogues."""
    bot_before = {}
    for d in dialogues:
        for ti, _, _, bot in user_turns(d):
            bot_before[(d["dialogue_id"], ti)] = bot
    per = collections.defaultdict(lambda: [0, 0, 0])
    x = make_extractor()
    for r in rows:
        out = x.extract(r["text"], intent_of_row(r), bot_before.get((r["dialogue_id"], r["turn"])), {})
        pred = char_to_word_spans(r["text"], [(k, v["start"], v["end"]) for k, v in out.items()])
        gold = spans_from_bio(r["ner_tags"])
        for s in pred & gold:
            per[s[2]][0] += 1
        for s in pred - gold:
            per[s[2]][1] += 1
        for s in gold - pred:
            per[s[2]][2] += 1

    def prf(tp, fp, fn):
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0,
                "support": tp + fn}
    tot = [sum(v[i] for v in per.values()) for i in range(3)]
    res = {k: prf(*v) for k, v in sorted(per.items())}
    res["MICRO"] = prf(*tot)
    ext = [sum(v[i] for k, v in per.items() if k in EXTRACTIVE) for i in range(3)]
    res["MICRO_extractive"] = prf(*ext)
    return res


# Slots whose value is a piece of the user's text, so span boundaries are comparable. The hybrid extractor
# maps purpose / service_mentioned / issue to standard categories ("land transfer", "driving license"),
# which span F1 cannot score fairly; those are judged in the dialogue-state results instead.
EXTRACTIVE = {"district", "date", "travel_date", "date_of_birth", "new_value"}


# ------------------------------------------------------------------ main
def print_dst(title, table):
    print(f"\n{title}")
    print(f"  {'tracker':20s}{'JGA':>8}{'slot JGA':>10}{'intent':>8}{'JGA core':>10}{'JGA turn2+':>12}{'slot F1':>9}")
    for name, r in table.items():
        print(f"  {name:20s}{r['jga']:>8}{r['slot_jga']:>10}{r['intent_acc']:>8}{str(r['jga_core_dialogues']):>10}"
              f"{str(r['jga_turn2plus']):>12}{r['slot_micro']['f1']:>9}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default="data/seed_all.json")
    ap.add_argument("--silver", default="data/synthetic/synthetic_dialogues.json")
    ap.add_argument("--gold-tokens", default="data/gold_tokens.jsonl")
    ap.add_argument("--fresh-tokens", default="data/fresh_tokens.jsonl")
    ap.add_argument("--fresh-dialogues", default="data/fresh_dialogues.json")
    ap.add_argument("--xlmr-dir", default=None, help="e.g. models/c1/run_seed1 (adds XLM-R intent and NER)")
    ap.add_argument("--fresh-states", default="data/fresh_dialogues_states.json",
                    help="fresh dialogues with hand-labelled slot states (held-out JGA test)")
    ap.add_argument("--make-fresh-template", action="store_true",
                    help="write data/fresh_dialogues_states.json with empty slots to fill in by hand, then stop")
    ap.add_argument("--out", default="results/dst_results.json")
    a = ap.parse_args()

    if a.make_fresh_template:
        if os.path.exists(a.fresh_states):
            sys.exit(f"{a.fresh_states} already exists; not overwriting it.")
        dlg = load_json(a.fresh_dialogues)
        for d in dlg:
            for t in d["turns"]:
                if t.get("speaker") == "user":
                    t["state"] = {"intent": t.get("state", {}).get("intent"), "slots": {}, "labelled": False}
        with open(a.fresh_states, "w", encoding="utf-8") as fh:
            json.dump(dlg, fh, ensure_ascii=False, indent=2)
        sys.exit(f"wrote {a.fresh_states}: fill in 'slots' for every user turn (cumulative), then rerun without the flag")

    if not os.path.exists(a.gold):
        sys.exit(f"{a.gold} not found. Run from research/ (python experiments/prepare_labelstudio.py builds it).")
    gold = load_json(a.gold)
    silver = load_json(a.silver) if os.path.exists(a.silver) else []
    results = {"run_at": time.strftime("%Y-%m-%d %H:%M"), "window": WINDOW, "gold_dialogues": len(gold),
               "silver_dialogues": len(silver), "dst_gold": {}, "dst_silver": {}, "spans": {}}

    xl = XLMR(a.xlmr_dir) if a.xlmr_dir else None
    settings = tracker_settings(xl.ner if xl else None)

    sources = {"oracle": [s.get("intent") for d in gold for _, _, s, _ in user_turns(d)]}
    if silver:
        sources["tfidf_w3"] = tfidf_intent(silver)(window_inputs(gold))
    if xl:
        sources["xlmr_w3"] = xl.predict_intent(window_inputs(gold))

    for src, intents in sources.items():
        table = {}
        for name, make in settings.items():
            if name.startswith(("1_", "2_", "3_")) and src != "oracle":
                continue          # ablation only with oracle intent
            table[name] = run_dst(gold, intents, make)
        results["dst_gold"][src] = table
        print_dst(f"Gold dialogues ({sum(len(user_turns(d)) for d in gold)} user turns), intent = {src}", table)

    if silver:
        intents = [s.get("intent") for d in silver for _, _, s, _ in user_turns(d)]
        table = {n: run_dst(silver, intents, m) for n, m in settings.items()}
        results["dst_silver"]["oracle"] = table
        print_dst(f"Synthetic dialogues ({len(intents)} user turns; NOT used to write the rules), intent = oracle", table)

    # held-out test: fresh dialogues with hand-labelled states (only once every user turn has been filled in)
    if os.path.exists(a.fresh_states):
        fresh_dlg = load_json(a.fresh_states)
        labelled = all(t.get("state", {}).get("labelled") for d in fresh_dlg for t in d["turns"]
                       if t.get("speaker") == "user")
        if labelled:
            results["dst_fresh"] = {}
            src = {"oracle": [s.get("intent") for d in fresh_dlg for _, _, s, _ in user_turns(d)]}
            if silver:
                src["tfidf_w3"] = tfidf_intent(silver)(window_inputs(fresh_dlg))
            if xl:
                src["xlmr_w3"] = xl.predict_intent(window_inputs(fresh_dlg))
            for name, intents in src.items():
                table = {n: run_dst(fresh_dlg, intents, m) for n, m in settings.items()
                         if name == "oracle" or not n.startswith(("1_", "2_", "3_"))}
                results["dst_fresh"][name] = table
                print_dst(f"Fresh dialogues (held-out, hand-labelled states), intent = {name}", table)
        else:
            print(f"\n{a.fresh_states}: not every user turn has \"labelled\": true yet, so the fresh JGA is skipped.")

    # span-level entity F1 (same metric as the XLM-R NER results in Observation 7)
    makers = {"hybrid": lambda: SlotExtractor()}
    if xl:
        makers["xlmr_ner"] = lambda: NerOnlyExtractor(xl.ner)
        makers["hybrid+xlmr"] = lambda: SlotExtractor(ner=xl.ner)
    for name, tok_path, dlg in [("gold", a.gold_tokens, gold),
                                ("fresh", a.fresh_tokens, load_json(a.fresh_dialogues)
                                 if os.path.exists(a.fresh_dialogues) else [])]:
        if not os.path.exists(tok_path):
            continue
        rows = load_jsonl(tok_path)
        results["spans"][name] = {m: span_eval(rows, dlg, mk, lambda r: r["intent"]) for m, mk in makers.items()}
        print(f"\nEntity spans, {name} set (intent = gold label). XLM-R NER reference, 3-seed mean from Observation 7: "
              f"all types gold 0.528 / fresh 0.394; extractive types gold 0.655 / fresh 0.481")
        for m, rep in results["spans"][name].items():
            print(f"  {m:12s} micro-F1 all types {rep['MICRO']['f1']} (n={rep['MICRO']['support']}) | "
                  f"extractive types {rep['MICRO_extractive']['f1']} (P {rep['MICRO_extractive']['precision']}, "
                  f"R {rep['MICRO_extractive']['recall']}, n={rep['MICRO_extractive']['support']})")
            print("     " + ", ".join(f"{k} {v['f1']}" for k, v in rep.items() if not k.startswith("MICRO")))

    best = results["dst_gold"].get("tfidf_w3", results["dst_gold"]["oracle"]).get("4_full")
    print("\nPer-slot scores (gold, full tracker" + (", TF-IDF intent):" if "tfidf_w3" in results["dst_gold"] else "):"))
    for s, v in best["per_slot"].items():
        print(f"  {s:18s}P {v['precision']:<7}R {v['recall']:<7}F1 {v['f1']:<7}n={v['support']}")

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
    print("\nsaved", a.out)


if __name__ == "__main__":
    main()
