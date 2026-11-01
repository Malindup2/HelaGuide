"""
H4 robustness: does the hybrid tracker (rules + XLM-R NER fallback) degrade less than the rules alone on messy input?

Builds perturbed copies of the fresh test set and the held-out synthetic test set (the test part of
data/synthetic/context_v2_split.json, the same split as the context v2 experiment) and runs the dialogue state
tracker on the clean and the perturbed text, with the gold intent so that only slot tracking is measured:
  (a) rules only               DialogueStateTracker(SlotExtractor())
  (b) hybrid with NER fallback DialogueStateTracker(SlotExtractor(ner=XLM-R NER of run_v2_seed1))

Perturbations (hand-written lists in data/perturb_lexicon.json, fixed seed, several draws):
  romanisation  spelling variants of common Singlish words (aluth -> alut, ikmanata -> ikmanta, one -> oney) and of
                district names (the only perturbation that changes NE tokens, and only through that table)
  typos         one character dropped or two neighbours swapped in ~15% of SI / EN / MIXED words (never NE / OTHER)
  script_swap   common words between romanised and Sinhala script (mata <-> මට)
  code_mix      some words swapped between Sinhala and English (aluth -> new, urgent -> ikmanata)
Words inside gold free-text spans (new_value, purpose, service_mentioned, issue) are never changed, because their
gold values are the literal words. One word is replaced by one word, so the entity tags stay aligned.

Metrics: JGA and span F1 on the extractive slots (district, dates, new_value), clean and per perturbation.
H4 statistic per turn: (JGA drop of rules) - (JGA drop of hybrid), drop = clean - perturbed; 95% CI by cluster
bootstrap over dialogues. Fresh is the headline. The NER model was trained on most synthetic dialogues, so the hybrid
results on synthetic are marked INVALID (the rules-only numbers there are valid: the rules never saw them).

Run from research/ (CPU, about 3-5 minutes):
    python experiments/perturb.py --out-dir results/context_v2
    python experiments/perturb.py --no-ner ...       # rules only (no model needed), for a dry run
Writes robustness.csv, robustness.png and perturbed/<set>__<perturbation>__draw<k>.jsonl in --out-dir;
context_eval.py puts H4 into summary.md from robustness.csv.
"""
import argparse
import collections
import json
import os
import random
import sys
import time
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import context_strategies as cs  # noqa: E402
from c1_dst import (DISTRICTS, FREE_TEXT, DialogueStateTracker, SlotExtractor, _DATE_LOOKUP, low, norm,  # noqa: E402
                    states_match, words_with_offsets)
from context_eval import SERIES, Bootstrap, _style, prf, write_csv  # noqa: E402
from dst_eval import EXTRACTIVE, char_to_word_spans, load_json, load_jsonl, spans_from_bio, user_turns  # noqa: E402

PERTURBATIONS = ["romanisation", "typos", "script_swap", "code_mix"]
POOLED = "all_perturbations"
LEXICON = "data/perturb_lexicon.json"
SEED, DRAWS = 20261023, 5
MIN_TURNS = 30
FILES = {"fresh": ("data/fresh_tokens.jsonl", "data/fresh_dialogues_states.json"),
         "synthetic": ("data/synthetic/silver_tokens.jsonl", "data/synthetic/synthetic_dialogues.json")}
VALID_HYBRID = {"fresh": True, "synthetic": False}       # run_v2_seed1's NER was trained on 90% of the silver set
KNOWN_FORMS = ({low(f) for f in cs.CUE_FORMS} | {low(f) for forms in DISTRICTS.values() for f in forms}
               | set(_DATE_LOOKUP))                       # spellings the tracker's lists already contain


# ------------------------------------------------------------------ perturbations
def load_lexicon(path=LEXICON):
    with open(path, encoding="utf-8") as fh:
        lex = json.load(fh)
    pairs = lex["script_pairs"]
    lex["script_map"] = {**pairs, **{v: k for k, v in pairs.items()}}       # both directions
    return lex


def _protected(ner_tags):
    """Words inside gold free-text spans: their gold value is the literal text, so they are never changed."""
    return [t != "O" and t[2:] in FREE_TEXT for t in ner_tags]


def _keep_case(old, new):
    return new[0].upper() + new[1:] if old[:1].isupper() and new[:1].islower() else new


def _typo(word, rng):
    if len(word) < 3:
        return word
    if rng.random() < 0.5:
        p = rng.randrange(len(word))
        return word[:p] + word[p + 1:]
    p = rng.randrange(len(word) - 1)
    swapped = word[:p] + word[p + 1] + word[p] + word[p + 2:]
    return swapped if swapped != word else word[:p] + word[p + 1:]


def perturb_row(row, kind, lex, rng):
    """A perturbed copy of one token row (same number of words, same entity tags). Adds `changed` (word indices)."""
    tokens, tags = list(row["tokens"]), list(row["lang_tags"])
    protected = _protected(row["ner_tags"])
    rate = lex["rates"][kind if kind != "typos" else "typo"]
    changed = []
    for i, (w, t) in enumerate(zip(tokens, tags)):
        if protected[i]:
            continue
        lw, new, new_tag = low(w), None, t
        if kind == "romanisation":
            if t == "SI" and lw in lex["romanisation"]:
                new = rng.choice(lex["romanisation"][lw])
            elif t == "NE" and lw in lex["district_spellings"]:           # the only change to an NE token
                new = rng.choice(lex["district_spellings"][lw])
        elif kind == "typos":
            if t in ("SI", "EN", "MIXED") and len(w) >= 3:
                new = _typo(w, rng)
        elif kind == "script_swap":
            if t == "SI" and lw in lex["script_map"]:
                new = lex["script_map"][lw]
        elif kind == "code_mix":
            if t == "SI" and lw in lex["code_mix"]["si_to_en"]:
                new, new_tag = lex["code_mix"]["si_to_en"][lw], "EN"
            elif t == "EN" and lw in lex["code_mix"]["en_to_si"]:
                new, new_tag = lex["code_mix"]["en_to_si"][lw], "SI"
        else:
            raise ValueError(kind)
        if new is None or rng.random() >= rate:
            continue
        new = _keep_case(w, new)
        if new and new != w:
            tokens[i], tags[i] = new, new_tag
            changed.append(i)
    # rebuild the text: replace each word in place, keeping spaces and punctuation
    text = norm(row["text"])
    spans = list(words_with_offsets(text))
    assert [x for x, _, _ in spans] == list(row["tokens"]), (row["dialogue_id"], row["turn"])
    for i in sorted(changed, reverse=True):
        _, s, e = spans[i]
        text = text[:s] + tokens[i] + text[e:]
    out = {**row, "text": text, "tokens": tokens, "lang_tags": tags, "changed": changed, "perturbation": kind,
           "new_form_known": [low(tokens[i]) in KNOWN_FORMS for i in changed]}
    if [x for x, _, _ in words_with_offsets(text)] != tokens:        # a new form that splits or merges words
        return {**row, "changed": [], "perturbation": kind, "new_form_known": []}
    return out


def perturb_set(rows, kind, lex, seed, draw):
    """Deterministic: every turn gets its own generator from (seed, draw, kind, dialogue, turn)."""
    out = []
    for r in rows:
        rng = random.Random(zlib.crc32(f"{seed}/{draw}/{kind}/{r['dialogue_id']}/{r['turn']}".encode()))
        out.append(perturb_row(r, kind, lex, rng))
    return out


# ------------------------------------------------------------------ evaluation
def load_test_set(name):
    tok_path, dlg_path = FILES[name]
    rows = load_jsonl(tok_path)
    if name == "synthetic":
        test = set(load_json(cs.SPLIT_PATH)["test"])
        rows = [r for r in rows if r["dialogue_id"] in test]
    rows.sort(key=lambda r: (r["dialogue_id"], r["turn"]))
    states, bot = {}, {}
    for d in load_json(dlg_path):
        for i, _, state, b in user_turns(d):
            states[(d["dialogue_id"], i)], bot[(d["dialogue_id"], i)] = state, b
    return rows, states, bot


def run_tracker(rows, states, bot, make_extractor):
    """Per turn: JGA correct (gold intent) and extractive span counts (tp, fp, fn). Reset at every dialogue."""
    jga, spans, trk, cur = [], [], None, None
    for r in rows:
        if r["dialogue_id"] != cur:
            trk, cur = DialogueStateTracker(make_extractor()), r["dialogue_id"]
        gold = states[(r["dialogue_id"], r["turn"])]
        pred = trk.update(r["text"], gold.get("intent"), bot[(r["dialogue_id"], r["turn"])])
        jga.append(pred["intent"] == gold.get("intent") and states_match(pred["slots"], gold.get("slots", {}) or {}, True))
        ps = char_to_word_spans(r["text"], [(k, v["start"], v["end"]) for k, v in trk.spans.items()
                                            if k in EXTRACTIVE and v["start"] is not None])
        gs = {s for s in spans_from_bio(r["ner_tags"]) if s[2] in EXTRACTIVE}
        spans.append((len(ps & gs), len(ps - gs), len(gs - ps)))
    return np.array(jga, float), np.array(spans)


def h4_row_verdict(n, lo, hi, valid):
    if not valid:
        return "INVALID (NER trained on these dialogues)"
    if n < MIN_TURNS:
        return "inconclusive (< 30 turns)"
    if lo is None:
        return "inconclusive"
    if lo > 0:
        return "hybrid degrades less"
    if hi < 0:
        return "hybrid degrades more"
    return "inconclusive (CI crosses 0)"


def evaluate(test_sets, lex, seed, draws, ner, out_dir):
    trackers = {"rules": lambda: SlotExtractor()}
    if ner is not None:
        cache = {}

        def cached_ner(text):
            if text not in cache:
                cache[text] = ner(text)
            return cache[text]
        trackers["hybrid"] = lambda: SlotExtractor(ner=cached_ner)
    rows_out = []
    os.makedirs(os.path.join(out_dir, "perturbed"), exist_ok=True)
    for ts in test_sets:
        rows, states, bot = load_test_set(ts)
        names = {}
        boots = Bootstrap([names.setdefault(r["dialogue_id"], len(names)) for r in rows], seed=seed)
        clean = {k: run_tracker(rows, states, bot, f) for k, f in trackers.items()}
        per = {}                                   # perturbation -> tracker -> (draw-mean JGA per turn, span sums)
        stats = {}
        for kind in PERTURBATIONS:
            acc = {k: [] for k in trackers}
            span = {k: np.zeros(3) for k in trackers}
            n_words = n_changed = n_known = 0
            for draw in range(draws):
                prow = perturb_set(rows, kind, lex, seed, draw)
                with open(os.path.join(out_dir, "perturbed", f"{ts}__{kind}__draw{draw}.jsonl"), "w", encoding="utf-8") as fh:
                    for r in prow:
                        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                n_words += sum(len(r["tokens"]) for r in prow)
                n_changed += sum(len(r["changed"]) for r in prow)
                n_known += sum(sum(r["new_form_known"]) for r in prow)
                for k, f in trackers.items():
                    j, sp = run_tracker(prow, states, bot, f)
                    acc[k].append(j)
                    span[k] += sp.sum(axis=0)
            per[kind] = {k: (np.mean(acc[k], axis=0), span[k]) for k in trackers}
            stats[kind] = {"words_changed_share": round(n_changed / max(1, n_words), 4),
                           "new_form_known_share": round(n_known / max(1, n_changed), 4)}
        per[POOLED] = {k: (np.mean([per[p][k][0] for p in PERTURBATIONS], axis=0),
                           sum(per[p][k][1] for p in PERTURBATIONS)) for k in trackers}
        stats[POOLED] = {"words_changed_share": round(np.mean([stats[p]["words_changed_share"] for p in PERTURBATIONS]), 4),
                         "new_form_known_share": round(np.mean([stats[p]["new_form_known_share"] for p in PERTURBATIONS]), 4)}
        valid = VALID_HYBRID[ts]
        base = {"test_set": ts, "perturbation": "clean", "turns": len(rows), "dialogues": len(names), "draws": 1,
                "words_changed_share": 0.0, "new_form_known_share": None,
                "rules_jga": round(float(clean["rules"][0].mean()), 4),
                "rules_span_f1": prf(*clean["rules"][1].sum(axis=0))["f1"]}
        if "hybrid" in trackers:
            base.update(hybrid_jga=round(float(clean["hybrid"][0].mean()), 4),
                        hybrid_span_f1=prf(*clean["hybrid"][1].sum(axis=0))["f1"])
        rows_out.append({**base, "valid": "rules valid" + ("" if valid else "; hybrid INVALID")})
        for kind in PERTURBATIONS + [POOLED]:
            r = {**base, "perturbation": kind, "draws": draws, **stats[kind],
                 "rules_jga": round(float(per[kind]["rules"][0].mean()), 4),
                 "rules_span_f1": prf(*per[kind]["rules"][1])["f1"],
                 "rules_drop": round(float(clean["rules"][0].mean() - per[kind]["rules"][0].mean()), 4)}
            if "hybrid" in trackers:
                d = (clean["rules"][0] - per[kind]["rules"][0]) - (clean["hybrid"][0] - per[kind]["hybrid"][0])
                lo, hi = boots.mean_ci(d)
                r.update(hybrid_jga=round(float(per[kind]["hybrid"][0].mean()), 4),
                         hybrid_span_f1=prf(*per[kind]["hybrid"][1])["f1"],
                         hybrid_drop=round(float(clean["hybrid"][0].mean() - per[kind]["hybrid"][0].mean()), 4),
                         delta=round(float(d.mean()), 4), ci95_low=lo, ci95_high=hi,
                         verdict=h4_row_verdict(len(rows), lo, hi, valid))
            r["valid"] = "rules valid" + ("" if valid else "; hybrid INVALID")
            rows_out.append(r)
    head = next((r for r in rows_out if r["test_set"] == "fresh" and r["perturbation"] == POOLED and "delta" in r), None)
    if head:
        v = head["verdict"]
        head["h4_verdict"] = ("supported" if v == "hybrid degrades less" else
                              "not supported" if v == "hybrid degrades more" else v)
    return rows_out


def plot(rows, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _style(plt)
    sets = list(dict.fromkeys(r["test_set"] for r in rows))
    kinds = ["clean"] + PERTURBATIONS + [POOLED]
    fig, axes = plt.subplots(1, len(sets), figsize=(6.4 * len(sets), 4.4), squeeze=False, sharey=True)
    for ax, ts in zip(axes[0], sets):
        by = {r["perturbation"]: r for r in rows if r["test_set"] == ts}
        valid = VALID_HYBRID[ts]
        series = [("rules", "rules only", SERIES[0])] + ([("hybrid", "rules + XLM-R NER", SERIES[1])]
                                                          if "hybrid_jga" in by["clean"] else [])
        w = 0.8 / len(series)
        for j, (k, label, colour) in enumerate(series):
            xs = [i + (j - (len(series) - 1) / 2) * w for i in range(len(kinds))]
            ax.bar(xs, [by[x][f"{k}_jga"] for x in kinds], w * 0.92, color=colour,
                   hatch="///" if k == "hybrid" and not valid else None, edgecolor="#fcfcfb", linewidth=0,
                   label=label + (" (INVALID here)" if k == "hybrid" and not valid else ""))
        ax.set_xticks(range(len(kinds)))
        ax.set_xticklabels([k.replace("_", "\n") for k in kinds], fontsize=8)
        ax.set_ylim(0, 1.05)
        ax.set_ylabel("JGA (gold intent)")
        head = by.get(POOLED, {})
        sub = (f"rules drop − hybrid drop (> 0 = hybrid degrades less): {head['delta']:+.3f} [{head['ci95_low']:+.3f}, {head['ci95_high']:+.3f}]"
               if valid and head.get("ci95_low") is not None else ("hybrid INVALID: NER trained on these dialogues"
                                                                   if not valid else ""))
        ax.set_title(f"{ts} ({by['clean']['turns']} turns)\n{sub}", loc="left", fontsize=9)
        ax.grid(axis="x", visible=False)
        ax.legend(frameon=False, fontsize=8, loc="lower left")
    fig.suptitle("H4: tracker robustness to messy input (JGA, mean over draws)", x=0.01, ha="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out-dir", default="results/context_v2")
    ap.add_argument("--model-dir", default="models/c1/run_v2_seed1", help="XLM-R NER for the hybrid tracker")
    ap.add_argument("--test-set", choices=["fresh", "synthetic", "both"], default="both")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--draws", type=int, default=DRAWS, help="perturbation draws per set (all from --seed)")
    ap.add_argument("--no-ner", action="store_true", help="rules only (no model needed)")
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args(argv)
    os.makedirs(a.out_dir, exist_ok=True)
    outs = [os.path.join(a.out_dir, f) for f in ("robustness.csv", "robustness.png")]
    if any(os.path.exists(p) for p in outs) and not a.overwrite:
        sys.exit(f"{a.out_dir} already has robustness.*; pass --overwrite")
    t0 = time.time()
    ner = None
    if not a.no_ner:
        from dst_eval import XLMR
        ner = XLMR(a.model_dir).ner
    test_sets = ["fresh", "synthetic"] if a.test_set == "both" else [a.test_set]
    rows = evaluate(test_sets, load_lexicon(), a.seed, a.draws, ner, a.out_dir)
    fields = list(dict.fromkeys(k for r in rows for k in r))      # the clean rows have no drop / CI columns
    write_csv(outs[0], [{k: r.get(k, "") for k in fields} for r in rows])
    plot(rows, outs[1])
    cols = ["test_set", "perturbation", "words_changed_share", "rules_jga", "hybrid_jga", "rules_drop", "hybrid_drop",
            "delta", "ci95_low", "ci95_high", "verdict"]
    print("  ".join(f"{c:>14s}" for c in cols))
    for r in rows:
        print("  ".join(f"{str(r.get(c, '')):>14s}"[:max(14, len(str(r.get(c, ''))))] for c in cols))
    print(f"\nwrote {outs[0]}, {outs[1]} and perturbed/ in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
