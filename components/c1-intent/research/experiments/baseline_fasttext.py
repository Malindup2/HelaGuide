r"""
Convert the Label Studio export into a token-level gold dataset and run the
fastText language-ID baseline on it.

Before running:
    Label Studio -> project -> Export -> JSON -> save as data\ls_export.json

Run from components/c1-intent/research/:
    conda activate nlp
    python experiments\baseline_fasttext.py

Outputs:
    data/gold_tokens.jsonl            one line per user turn: tokens, language tags, BIO entity tags
    results/baseline_fasttext.json    all numbers below, for your report
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

DATA = Path("data")
RESULTS = Path("results")
MODEL = Path("models/lid.176.bin")

sys.path.insert(0, str(Path(__file__).parent))
from prepare_labelstudio import guess_lang, words_with_offsets  # same tokenisation as labelling


# ------------------------------------------------------------------ loading
def overlap(a0, a1, b0, b1):
    return max(0, min(a1, b1) - max(a0, b0))


def submitted_result(task):
    """The latest non-cancelled human annotation, or None."""
    anns = [a for a in task.get("annotations", []) if not a.get("was_cancelled")]
    if not anns:
        return None
    anns.sort(key=lambda a: a.get("updated_at") or a.get("created_at") or "")
    return anns[-1].get("result", [])


def to_example(task, result):
    text = task["data"]["text"]
    words = list(words_with_offsets(text))
    lang_regions = [r["value"] for r in result if r.get("from_name") == "lang"]
    ent_regions = [r["value"] for r in result if r.get("from_name") == "slot"]

    tokens, lang, ner = [], [], []
    prev_ent = None
    for w, s, e in words:
        tokens.append(w)
        best = max(lang_regions, key=lambda v: overlap(s, e, v["start"], v["end"]), default=None)
        lang.append(best["labels"][0] if best and overlap(s, e, best["start"], best["end"]) else "UNLABELLED")

        hit = next((v for v in ent_regions if overlap(s, e, v["start"], v["end"])), None)
        if hit is None:
            ner.append("O")
            prev_ent = None
        else:
            tag = hit["labels"][0]
            ner.append(("I-" if prev_ent is hit else "B-") + tag)
            prev_ent = hit

    d = task["data"]
    return {
        "dialogue_id": d.get("dialogue_id"), "turn": d.get("turn"), "intent": d.get("intent"),
        "code_mix": d.get("code_mix"), "text": text, "tokens": tokens,
        "lang_tags": lang, "ner_tags": ner,
    }


def script_of(tokens):
    has_si = any(any("඀" <= c <= "෿" for c in t) for t in tokens)
    return "sinhala_script" if has_si else "romanized"


# ------------------------------------------------------------------ fastText
FT_MAP = {"__label__si": "SI", "__label__en": "EN"}


def ft_label(model, text):
    labels, _ = model.predict(text.replace("\n", " "), k=1)
    return FT_MAP.get(labels[0], "OTHER_LANG")


def accuracy(pairs):
    return round(sum(g == p for g, p in pairs) / len(pairs), 4) if pairs else None


def main():
    export = DATA / "ls_export.json"
    if not export.exists():
        sys.exit("data/ls_export.json not found. Export from Label Studio (JSON) and save it there.")
    with open(export, encoding="utf-8") as fh:
        tasks = json.load(fh)

    # Intents come from the current dialogue files (Label Studio tasks may predate schema v1).
    # Without them the gold set would silently carry the old intents from the export.
    current = {}
    seed_all = DATA / "seed_all.json"
    if not seed_all.exists():
        sys.exit("data/seed_all.json not found. Run prepare_labelstudio.py first so intents "
                 "come from the current dialogue files, not the Label Studio export.")
    with open(seed_all, encoding="utf-8") as fh:
        for d in json.load(fh):
            for i, turn in enumerate(d["turns"]):
                if "state" in turn:
                    current[(d["dialogue_id"], i)] = turn["state"].get("intent")

    examples, missing, stale_intent = [], 0, 0
    heur_pairs = []
    for t in tasks:
        res = submitted_result(t)
        if res is None:
            missing += 1
            continue
        ex = to_example(t, res)
        key = (ex["dialogue_id"], ex["turn"])
        if key in current:
            ex["intent"] = current[key]
        else:
            stale_intent += 1
        examples.append(ex)
        heur_pairs += [(g, guess_lang(w)) for w, g in zip(ex["tokens"], ex["lang_tags"])]

    DATA.mkdir(exist_ok=True)
    with open(DATA / "gold_tokens.jsonl", "w", encoding="utf-8") as fh:
        for ex in examples:
            fh.write(json.dumps(ex, ensure_ascii=False) + "\n")

    all_tags = Counter(tag for ex in examples for tag in ex["lang_tags"])
    ent_tags = Counter(t[2:] for ex in examples for t in ex["ner_tags"] if t.startswith("B-"))
    changed = sum(g != p for g, p in heur_pairs)

    print(f"Tasks in export: {len(tasks)}   submitted: {len(examples)}   not submitted: {missing}")
    print(f"Tokens: {sum(all_tags.values())}   language tags: {dict(all_tags)}")
    print(f"Entities: {dict(ent_tags)}")
    print(f"Pre-label corrections: {changed} of {len(heur_pairs)} language tags changed by you "
          f"(heuristic accuracy {accuracy(heur_pairs)})")
    if stale_intent:
        print(f"WARNING: {stale_intent} turns not found in data/seed_all.json; "
              "their intent is taken from the Label Studio export and may be out of date.")
    if all_tags.get("UNLABELLED"):
        print(f"WARNING: {all_tags['UNLABELLED']} tokens have no language tag. Check those tasks.")

    results = {
        "n_turns": len(examples), "n_tokens": sum(all_tags.values()),
        "lang_tag_counts": dict(all_tags), "entity_counts": dict(ent_tags),
        "heuristic_prelabel_accuracy": accuracy(heur_pairs), "heuristic_tags_corrected": changed,
    }

    if not MODEL.exists():
        print(f"\n{MODEL} not found, skipping fastText.")
    else:
        import fasttext
        model = fasttext.load_model(str(MODEL))

        # Token level: only SI/EN gold tokens (NE, OTHER, MIXED have no fastText equivalent)
        tok = defaultdict(list)
        for ex in examples:
            grp = f"{ex['code_mix']} / {script_of(ex['tokens'])}"
            for w, g in zip(ex["tokens"], ex["lang_tags"]):
                if g in ("SI", "EN"):
                    pair = (g, ft_label(model, w))
                    tok["ALL"].append(pair)
                    tok[grp].append(pair)
                    tok[f"gold={g}"].append(pair)

        # Sentence level: fastText's one label vs the majority SI/EN tag in the turn
        sent = defaultdict(list)
        for ex in examples:
            si_en = [g for g in ex["lang_tags"] if g in ("SI", "EN")]
            if not si_en:
                continue
            gold = Counter(si_en).most_common(1)[0][0]
            pair = (gold, ft_label(model, ex["text"]))
            sent["ALL"].append(pair)
            sent[f"{ex['code_mix']} / {script_of(ex['tokens'])}"].append(pair)

        # How often does one sentence label erase a language that is actually present?
        mixed_turns = [ex for ex in examples if {"SI", "EN"} <= set(ex["lang_tags"])]

        results["fasttext_token_accuracy"] = {k: {"acc": accuracy(v), "n": len(v)} for k, v in sorted(tok.items())}
        results["fasttext_sentence_accuracy"] = {k: {"acc": accuracy(v), "n": len(v)} for k, v in sorted(sent.items())}
        results["turns_containing_both_SI_and_EN"] = len(mixed_turns)

        print("\nfastText TOKEN-level accuracy (SI/EN tokens only)")
        for k, v in sorted(tok.items()):
            print(f"  {k:32s}{accuracy(v):>7}   n={len(v)}")
        print("\nfastText SENTENCE-level accuracy (vs majority tag)")
        for k, v in sorted(sent.items()):
            print(f"  {k:32s}{accuracy(v):>7}   n={len(v)}")
        print(f"\n{len(mixed_turns)} of {len(examples)} turns contain both SI and EN words; "
              "a single sentence label is wrong for part of every one of them.")

    RESULTS.mkdir(exist_ok=True)
    with open(RESULTS / "baseline_fasttext.json", "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
    print("\nSaved data/gold_tokens.jsonl and results/baseline_fasttext.json")


if __name__ == "__main__":
    main()
