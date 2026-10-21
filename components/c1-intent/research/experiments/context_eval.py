"""
Context strategies v2 (sub-objective 3): joint goal accuracy per strategy, code-mixing breakdown, statistics and an
automatic hypothesis summary, from the per-turn predictions saved by c1_context_experiment.ipynb.

Run from research/ (CPU, no models needed):
    python experiments/context_eval.py --preds-dir results/context_v2/preds --out-dir results/context_v2
    python experiments/context_eval.py --test-set fresh ...          # one test set only
    python tests/fixtures/fake_context_preds.py --out <dir>          # fake predictions for a dry run

What it does
  1. Each run's predicted intents go turn by turn through the full DialogueStateTracker (rules, bot text passed in).
     Gold slot states are cumulative per original dialogue, so the tracker is reset at every dialogue boundary
     inside a stitched session; the intent model still saw the earlier dialogues through its context.
     Metrics: JGA, intent accuracy, both on intent-switch turns, per-slot F1, span F1 on the extractive slots
     (district, dates, new_value), context tokens and latency.
  2. Code-Mixing Index per turn from the language tags in the token files (gold for gold/fresh, LLM or hand-checked
     for synthetic): CMI = 100 * (1 - max_lang / (n - u)), u = NE + OTHER words, languages SI / EN / MIXED,
     CMI = 0 if n == u. Buckets: pure SI, pure EN, low CMI, high CMI (mixed turns split at the median CMI of the
     test set), plus NE/OTHER-only turns; separately Sinhala script / romanised / mixed script.
  3. Statistics: mean +- std over seeds; 95% CI by cluster bootstrap over sessions (1000 resamples, fixed seed,
     the same resamples for every strategy so differences are paired); exact McNemar on per-turn correctness
     (majority over seeds) against full_history (and against current_only for H1), Holm-corrected per model,
     test set and metric.
  4. H3 interaction: drop(S, bucket) = acc(full_history) - acc(S); the difference in drop between high-CMI and
     monolingual (pure SI + pure EN) turns, with a cluster-bootstrap CI. Headline: stratified by turn position
     (within first turns and within follow-up turns, weighted by their turn counts); also all turns pooled and
     follow-up turns only.
  5. Writes context_jga_results.json, stats_tests.csv, cmi_breakdown.csv/.png, interaction_tests.csv/.png,
     pareto_jga_vs_tokens.png, token_growth_by_turn_depth.png and summary.md (H1-H4 + scale claim).
     H4 and the scale claim are filled in from robustness.csv (perturb.py) and deployment_benchmark.csv
     (bench_cpu.py) in the same folder once those exist.
"""
import argparse
import collections
import csv
import glob
import json
import math
import os
import re
import statistics
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from c1_dst import DialogueStateTracker, SlotExtractor, states_match, values_match  # noqa: E402
from dst_eval import EXTRACTIVE, char_to_word_spans, load_json, load_jsonl, spans_from_bio, user_turns  # noqa: E402

STRATEGIES = ["current_only", "window_2", "window_3", "keyword_summary", "structured_state", "summary",
              "full_history"]
REFERENCE = "full_history"
BASELINE = "current_only"
H2_STRATEGIES = ["window_2", "window_3", "structured_state", "summary"]
MODELS = {"xlmr": "XLM-R", "tfidf": "TF-IDF + LogReg"}
HELD_OUT = ["synthetic", "fresh"]
POOLED = "heldout"                       # synthetic + fresh together
SET_LABEL = {"gold": "gold (dev set for the rules)", "synthetic": "synthetic (held out)", "fresh": "fresh (held out)",
             POOLED: "held-out (synthetic + fresh)"}
CMI_BUCKETS = ["pure_si", "pure_en", "low_cmi", "high_cmi", "ne_other_only"]
SCRIPT_BUCKETS = ["sinhala_script", "romanised", "mixed_script", "no_letters"]
MONO = ("pure_si", "pure_en")
H3_SCOPES = ("stratified", "all_turns", "follow_up")      # stratified by turn position is the H3 headline
H2_SENSITIVITY_MARGIN = 0.03
ORACLE = {"keyword_summary", "structured_state"}          # read gold language/entity tags at test time


def name(strategy):
    """Strategy name for reports; the oracle strategies are marked as upper bounds."""
    return f"{strategy} — oracle (gold tags at test time) — upper bound" if strategy in ORACLE else strategy
MIN_BUCKET = 30                          # fewer turns than this -> inconclusive
B_RESAMPLES, BOOT_SEED = 1000, 20261021
FILES = {"gold": ("data/seed_all.json", "data/gold_tokens.jsonl"),
         "synthetic": ("data/synthetic/synthetic_dialogues.json", "data/synthetic/silver_tokens.jsonl"),
         "fresh": ("data/fresh_dialogues_states.json", "data/fresh_tokens.jsonl")}
OUTPUTS = ["context_jga_results.json", "stats_tests.csv", "cmi_breakdown.csv", "cmi_breakdown.png",
           "interaction_tests.csv", "interaction_tests.png", "pareto_jga_vs_tokens.png",
           "token_growth_by_turn_depth.png", "summary.md"]


# ------------------------------------------------------------------ code-mixing
def cmi(tags):
    """Code-Mixing Index of one turn (Das & Gamback): 100 * (1 - max_lang / (n - u))."""
    n = len(tags)
    u = sum(t in ("NE", "OTHER") for t in tags)
    if n == u:
        return 0.0
    return 100.0 * (1 - max(sum(t == lang for t in tags) for lang in ("SI", "EN", "MIXED")) / (n - u))


def cmi_bucket(tags, value, threshold):
    """pure_si / pure_en / low_cmi / high_cmi / ne_other_only. threshold: median CMI of the mixed turns."""
    langs = [t for t in tags if t in ("SI", "EN", "MIXED")]
    if not langs:
        return "ne_other_only"
    if value == 0:
        return {"SI": "pure_si", "EN": "pure_en"}.get(langs[0], "low_cmi")    # MIXED-only: one mixed word
    return "high_cmi" if value > threshold else "low_cmi"


def script_bucket(text):
    si = any("඀" <= c <= "෿" for c in text)
    lat = bool(re.search(r"[A-Za-z]", text))
    return "mixed_script" if si and lat else "sinhala_script" if si else "romanised" if lat else "no_letters"


# ------------------------------------------------------------------ statistics
def mcnemar_exact(b, c):
    """Two-sided exact McNemar p-value from the discordant counts b and c."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def holm(ps):
    """Holm step-down adjusted p-values, in the input order."""
    m = len(ps)
    order = sorted(range(m), key=lambda i: ps[i])
    adj, run = [0.0] * m, 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (m - rank) * ps[i]))
        adj[i] = run
    return adj


class Bootstrap:
    """Cluster bootstrap over sessions. The same resamples are used for every statistic of a test set."""

    def __init__(self, session_idx, n_resamples=B_RESAMPLES, seed=BOOT_SEED):
        self.sid = np.asarray(session_idx)
        self.ns = int(self.sid.max()) + 1
        rng = np.random.default_rng(seed)
        self.w = rng.multinomial(self.ns, np.full(self.ns, 1 / self.ns), size=n_resamples).astype(float)

    def _ratio(self, values, mask):
        """Per-resample mean of `values` over the turns in `mask` (NaN when a resample has none)."""
        m = np.ones(len(self.sid)) if mask is None else np.asarray(mask, float)
        num = self.w @ np.bincount(self.sid, weights=np.asarray(values, float) * m, minlength=self.ns)
        den = self.w @ np.bincount(self.sid, weights=m, minlength=self.ns)
        with np.errstate(invalid="ignore", divide="ignore"):
            return num / den

    @staticmethod
    def _ci(samples, alpha=0.05):
        s = samples[~np.isnan(samples)]
        if not len(s):
            return [None, None]
        return [round(float(np.percentile(s, 100 * alpha / 2)), 4), round(float(np.percentile(s, 100 * (1 - alpha / 2))), 4)]

    def mean_ci(self, values, mask=None, alpha=0.05):
        return self._ci(self._ratio(values, mask), alpha)

    def diff_ci(self, a, b, mask=None, alpha=0.05):
        return self._ci(self._ratio(a, mask) - self._ratio(b, mask), alpha)

    def interaction_ci(self, full, red, high, mono, alpha=0.05):
        return self._ci(interaction_samples(self._ratio, full, red, high, mono), alpha)

    def count(self, mask):
        """Per-resample number of turns in `mask`."""
        return self.w @ np.bincount(self.sid, weights=np.asarray(mask, float), minlength=self.ns)

    def stratified_ci(self, full, red, high, mono, strata, alpha=0.05):
        """CI of the position-stratified interaction. Whole sessions are resampled, and every turn keeps its stratum."""
        return self._ci(stratified(self._ratio, self.count, full, red, high, mono, strata)[0], alpha)


def masked_mean(values, mask=None):
    v = np.asarray(values, float)
    m = np.ones(len(v), bool) if mask is None else np.asarray(mask, bool)
    return float(v[m].mean()) if m.any() else float("nan")


def interaction_samples(ratio, full, red, high, mono):
    """[drop(high) - drop(mono)] where drop = acc(full_history) - acc(reduced). `ratio` maps (values, mask) to a
    mean (or an array of resampled means)."""
    return (ratio(full, high) - ratio(red, high)) - (ratio(full, mono) - ratio(red, mono))


def stratified(ratio, count, full, red, high, mono, strata):
    """Position-stratified H3: the interaction within each stratum (first turns, follow-up turns), combined with
    weights = turns in high-CMI + monolingual within the stratum. Returns (diff, drop_high, drop_mono), each a
    number or an array of resampled values; a stratum that has no high-CMI or no monolingual turn in a resample
    is left out of that resample's average."""
    num = [0.0, 0.0, 0.0]
    den = 0.0
    for st in strata:
        h, m = high & st, mono & st
        dh, dm = ratio(full, h) - ratio(red, h), ratio(full, m) - ratio(red, m)
        w = count(h | m)
        ok = ~(np.isnan(dh) | np.isnan(dm))
        for i, v in enumerate((dh - dm, dh, dm)):
            num[i] = num[i] + np.where(ok, v * w, 0.0)
        den = den + np.where(ok, w, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return tuple(n / den for n in num)


def mean_std(xs):
    xs = [x for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))]
    if not xs:
        return [None, None]
    return [round(statistics.mean(xs), 4), round(statistics.stdev(xs), 4) if len(xs) > 1 else 0.0]


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0,
            "support": tp + fn}


# ------------------------------------------------------------------ loading
def load_preds(preds_dir):
    runs = {}
    paths = sorted(glob.glob(os.path.join(preds_dir, "*.jsonl")))
    if not paths:
        sys.exit(f"no *.jsonl prediction files in {preds_dir}")
    for p in paths:
        rows = load_jsonl(p)
        if not rows:
            continue
        key = (rows[0]["model"], rows[0]["strategy"], int(rows[0]["seed"]))
        if key in runs:
            sys.exit(f"two files for {key}: {p}")
        runs[key] = rows
    return runs


def load_reference(test_sets):
    """Gold states and token rows by (dialogue_id, turn index)."""
    states, tokens = {}, {}
    for ts in test_sets:
        dlg_path, tok_path = FILES[ts]
        for d in load_json(dlg_path):
            for i, _, state, _ in user_turns(d):
                states[(d["dialogue_id"], i)] = state
        for r in load_jsonl(tok_path):
            tokens[(r["dialogue_id"], r["turn"])] = r
    return states, tokens


def turn_table(runs, test_sets, tokens):
    """The test turns (identical in every run), in session order, with their CMI and script buckets."""
    first = next(iter(runs.values()))
    turns = sorted((r for r in first if r["test_set"] in test_sets),
                   key=lambda r: (test_sets.index(r["test_set"]), r["session_id"], r["session_pos"]))
    keys = [(r["test_set"], r["session_id"], r["session_pos"]) for r in turns]
    for k, rows in runs.items():
        got = sorted((r["test_set"], r["session_id"], r["session_pos"]) for r in rows if r["test_set"] in test_sets)
        if got != sorted(keys):
            sys.exit(f"run {k} has different test turns from {next(iter(runs))}")
    table, prev, prev_dlg = [], {}, {}
    for r in turns:
        tr = tokens.get((r["dialogue_id"], r["turn_index"]))
        if tr is None:
            sys.exit(f"no token row for {r['dialogue_id']}/{r['turn_index']}")
        tags = tr["lang_tags"]
        if any(t not in ("SI", "EN", "MIXED", "NE", "OTHER") for t in tags):
            sys.exit(f"{r['dialogue_id']}/{r['turn_index']}: missing language tags ({set(tags)})")
        p = prev.get(r["session_id"])
        table.append({"test_set": r["test_set"], "session_id": r["session_id"], "session_pos": r["session_pos"],
                      "dialogue_id": r["dialogue_id"], "turn_index": r["turn_index"], "text": r["text"],
                      "gold_intent": r["gold_intent"], "switch": p is not None and p != r["gold_intent"],
                      "follow_up": prev_dlg.get(r["session_id"]) == r["dialogue_id"],
                      "cmi": round(cmi(tags), 2), "tags": tags, "ner_tags": tr["ner_tags"],
                      "script": script_bucket(r["text"])})
        prev[r["session_id"]] = r["gold_intent"]
        prev_dlg[r["session_id"]] = r["dialogue_id"]
    return table


# ------------------------------------------------------------------ one run through the tracker
def eval_run(rows, table, states):
    """Per-turn correctness and slot counts for one (model, strategy, seed), in table order."""
    by = {(r["test_set"], r["session_id"], r["session_pos"]): r for r in rows}
    out = {"intent_ok": [], "jga_ok": [], "tokens_xlmr": [], "tokens_cl100k": [], "context_tokens_xlmr": [],
           "latency_ms": [], "span": [], "per_slot": collections.defaultdict(lambda: collections.defaultdict(
               lambda: [0, 0, 0]))}
    trk, cur = DialogueStateTracker(SlotExtractor()), None
    for t in table:
        r = by[(t["test_set"], t["session_id"], t["session_pos"])]
        if (t["session_id"], t["dialogue_id"]) != cur:          # gold states restart with every dialogue
            trk.reset()
            cur = (t["session_id"], t["dialogue_id"])
        pred = trk.update(r["text"], r["pred_intent"], r.get("bot_text"))
        gold = states[(t["dialogue_id"], t["turn_index"])]
        gs, ps = gold.get("slots", {}) or {}, pred["slots"]
        intent_ok = pred["intent"] == gold.get("intent")
        out["intent_ok"].append(intent_ok)
        out["jga_ok"].append(intent_ok and states_match(ps, gs, True))
        for k in ("tokens_xlmr", "tokens_cl100k", "context_tokens_xlmr", "latency_ms"):
            out[k].append(r[k])
        slot_counts = out["per_slot"][t["test_set"]]
        for slot in set(gs) | set(ps):
            if slot in gs and slot in ps and values_match(slot, ps[slot], gs[slot], True):
                slot_counts[slot][0] += 1
            else:
                slot_counts[slot][1] += slot in ps
                slot_counts[slot][2] += slot in gs
        pred_spans = char_to_word_spans(r["text"], [(k, v["start"], v["end"]) for k, v in trk.spans.items()
                                                    if k in EXTRACTIVE and v["start"] is not None])
        gold_spans = {s for s in spans_from_bio(t["ner_tags"]) if s[2] in EXTRACTIVE}
        out["span"].append((len(pred_spans & gold_spans), len(pred_spans - gold_spans), len(gold_spans - pred_spans)))
    return out


# ------------------------------------------------------------------ the analysis
def analyse(runs, table, states, ni_margin):
    sets = list(dict.fromkeys(t["test_set"] for t in table))
    if all(s in sets for s in HELD_OUT):
        sets.append(POOLED)
    models = [m for m in MODELS if any(k[0] == m for k in runs)]
    strategies = [s for s in STRATEGIES if any(k[1] == s for k in runs)]
    seeds = sorted({k[2] for k in runs})
    per_run = {k: eval_run(v, table, states) for k, v in runs.items()}

    members = {s: np.array([t["test_set"] == s or (s == POOLED and t["test_set"] in HELD_OUT) for t in table])
               for s in sets}
    thresholds, buckets = {}, {}
    for s in sets:
        idx = np.flatnonzero(members[s])
        mixed = [table[i]["cmi"] for i in idx if table[i]["cmi"] > 0]
        thresholds[s] = round(float(np.median(mixed)), 2) if mixed else None
        buckets[s] = {"cmi": [cmi_bucket(table[i]["tags"], table[i]["cmi"], thresholds[s] or 0) for i in idx],
                      "script": [table[i]["script"] for i in idx]}
    boots = {}
    for s in sets:
        idx = np.flatnonzero(members[s])
        names = {}
        sid = [names.setdefault(table[i]["session_id"], len(names)) for i in idx]
        boots[s] = Bootstrap(sid, seed=BOOT_SEED + sets.index(s))

    def vec(model, strategy, metric, s, seed=None):
        """Per-turn correctness on test set s: one seed, or the mean over seeds."""
        idx = members[s]
        rs = [per_run[(model, strategy, sd)][metric] for sd in seeds if (model, strategy, sd) in per_run
              and (seed is None or sd == seed)]
        return np.mean([np.asarray(r, float)[idx] for r in rs], axis=0) if rs else None

    res = {"settings": {"seeds": seeds, "models": models, "strategies": strategies, "test_sets": sets,
                        "bootstrap": {"resamples": B_RESAMPLES, "seed": BOOT_SEED, "cluster": "session"},
                        "mcnemar": "exact, per-turn correctness = majority over seeds, Holm per model x test set x metric",
                        "tracker": "DialogueStateTracker(SlotExtractor()), full setting, reset at dialogue boundaries",
                        "cmi_median_threshold": thresholds, "min_bucket_turns": MIN_BUCKET, "h2_ni_margin": ni_margin,
                        "fake_predictions": any(r.get("fake") for v in runs.values() for r in v[:1])},
           "turns": {s: {"n": int(members[s].sum()), "sessions": boots[s].ns,
                         "switch_turns": int(sum(t["switch"] for t, m in zip(table, members[s]) if m)),
                         "cmi_buckets": dict(collections.Counter(buckets[s]["cmi"])),
                         "script_buckets": dict(collections.Counter(buckets[s]["script"]))} for s in sets},
           "metrics": {}, "stats_tests": [], "interaction_tests": [], "cmi_breakdown": [], "token_growth": {}}

    for model in models:
        for st in strategies:
            for s in sets:
                idx = members[s]
                runs_ms = [(sd, per_run[(model, st, sd)]) for sd in seeds if (model, st, sd) in per_run]
                if not runs_ms:
                    continue
                switch = np.array([t["switch"] for t in table])[idx]
                per_seed = collections.defaultdict(list)
                slot_f1 = collections.defaultdict(list)
                for sd, r in runs_ms:
                    io, jo = np.asarray(r["intent_ok"], float)[idx], np.asarray(r["jga_ok"], float)[idx]
                    per_seed["jga"].append(jo.mean()); per_seed["intent_acc"].append(io.mean())
                    per_seed["switch_intent_acc"].append(io[switch].mean() if switch.any() else None)
                    per_seed["switch_jga"].append(jo[switch].mean() if switch.any() else None)
                    sp = np.asarray(r["span"])[idx].sum(axis=0)
                    per_seed["span_f1_extractive"].append(prf(*sp)["f1"])
                    counts = collections.defaultdict(lambda: [0, 0, 0])
                    for ts in ([s] if s != POOLED else HELD_OUT):
                        for slot, c in r["per_slot"][ts].items():
                            counts[slot] = [a + b for a, b in zip(counts[slot], c)]
                    for slot, c in counts.items():
                        slot_f1[slot].append((prf(*c)["f1"], c[0] + c[2]))
                    for k in ("tokens_xlmr", "tokens_cl100k", "context_tokens_xlmr", "latency_ms"):
                        v = np.asarray(r[k], float)[idx]
                        per_seed[k + "_mean"].append(v.mean()); per_seed[k + "_median"].append(float(np.median(v)))
                jv, iv = vec(model, st, "jga_ok", s), vec(model, st, "intent_ok", s)
                res["metrics"][f"{model}/{st}/{s}"] = {
                    "model": model, "strategy": st, "test_set": s, "n_turns": int(idx.sum()), "seeds": len(runs_ms),
                    **{k: mean_std(v) for k, v in per_seed.items()},
                    "jga_ci95": boots[s].mean_ci(jv), "intent_acc_ci95": boots[s].mean_ci(iv),
                    "per_slot_f1": {slot: {"f1": mean_std([f for f, _ in v]), "support": v[0][1]}
                                    for slot, v in sorted(slot_f1.items())},
                    "device": runs[(model, st, runs_ms[0][0])][0].get("device")}

    # paired tests against full_history (H2) and current_only (H1)
    for model in models:
        for s in sets:
            for metric, key in (("jga", "jga_ok"), ("intent_acc", "intent_ok")):
                for ref, family in ((REFERENCE, [x for x in strategies if x != REFERENCE]),
                                    (BASELINE, [x for x in strategies if x != BASELINE])):
                    rv = vec(model, ref, key, s)
                    if rv is None:
                        continue
                    rows = []
                    for st in family:
                        sv = vec(model, st, key, s)
                        if sv is None:
                            continue
                        a, b_ = sv > 0.5, rv > 0.5               # majority over seeds
                        b, c = int((a & ~b_).sum()), int((~a & b_).sum())
                        rows.append({"model": model, "test_set": s, "metric": metric, "strategy": st, "reference": ref,
                                     "n_turns": len(sv), "acc_strategy": round(float(sv.mean()), 4),
                                     "acc_reference": round(float(rv.mean()), 4),
                                     "diff": round(float(sv.mean() - rv.mean()), 4),
                                     "ci95_low": None, "ci95_high": None, "b_strategy_only": b, "c_reference_only": c,
                                     "p_exact": mcnemar_exact(b, c)})
                        rows[-1]["ci95_low"], rows[-1]["ci95_high"] = boots[s].diff_ci(sv, rv)
                    for r, p in zip(rows, holm([r["p_exact"] for r in rows])):
                        r["p_holm"], r["family_size"] = p, len(rows)
                        r["p_exact"] = round(r["p_exact"], 6); r["p_holm"] = round(p, 6)
                    res["stats_tests"] += rows

    # code-mixing and script buckets
    for model in models:
        for st in strategies:
            for s in sets:
                idx = members[s]
                for btype in ("cmi", "script"):
                    labels = np.array(buckets[s][btype])
                    for bucket in (CMI_BUCKETS if btype == "cmi" else SCRIPT_BUCKETS):
                        mask = labels == bucket
                        if not mask.any():
                            continue
                        row = {"model": model, "strategy": st, "test_set": s, "bucket_type": btype, "bucket": bucket,
                               "n_turns": int(mask.sum())}
                        per_seed = collections.defaultdict(list)
                        for sd in seeds:
                            r = per_run.get((model, st, sd))
                            if r is None:
                                continue
                            per_seed["jga"].append(np.asarray(r["jga_ok"], float)[idx][mask].mean())
                            per_seed["intent_acc"].append(np.asarray(r["intent_ok"], float)[idx][mask].mean())
                            per_seed["span_f1_extractive"].append(prf(*np.asarray(r["span"])[idx][mask].sum(axis=0))["f1"])
                            per_seed["tokens_xlmr_mean"].append(np.asarray(r["tokens_xlmr"], float)[idx][mask].mean())
                            per_seed["latency_ms_mean"].append(np.asarray(r["latency_ms"], float)[idx][mask].mean())
                        if not per_seed:
                            continue
                        for k, v in per_seed.items():
                            row[f"{k}_mean"], row[f"{k}_std"] = mean_std(v)
                        row["jga_ci95_low"], row["jga_ci95_high"] = boots[s].mean_ci(vec(model, st, "jga_ok", s), mask)
                        res["cmi_breakdown"].append(row)

    # H3: does the drop from full_history differ between high-CMI and monolingual turns? Short follow-up answers
    # ("ow", "Matara") are mostly monolingual and first requests mostly mixed, so turn position is confounded with
    # code-mixing. Three versions: stratified by position (first / follow-up turns, the headline), all turns
    # pooled, and follow-up turns only.
    k_family = max(1, len([x for x in strategies if x != REFERENCE]))
    n_count = lambda m: float(np.sum(m))
    for model in models:
        for s, scope in [(s, sc) for s in sets for sc in H3_SCOPES]:
            labels = np.array(buckets[s]["cmi"])
            follow = np.array([t["follow_up"] for t, m in zip(table, members[s]) if m])
            keep = follow if scope == "follow_up" else np.ones(len(labels), bool)
            high, mono = (labels == "high_cmi") & keep, np.isin(labels, MONO) & keep
            strata = [st for st in (~follow, follow) if (high & st).any() and (mono & st).any()]
            strata_note = " · ".join(f"{name} {int((high & st).sum())}/{int((mono & st).sum())}"
                                     for name, st in (("first", ~follow), ("follow-up", follow)))
            for metric, key in (("jga", "jga_ok"), ("intent_acc", "intent_ok")):
                fv = vec(model, REFERENCE, key, s)
                if fv is None:
                    continue
                for st in strategies:
                    if st == REFERENCE or vec(model, st, key, s) is None:
                        continue
                    sv = vec(model, st, key, s)
                    if scope == "stratified":
                        est, dh, dm = (float(x) for x in stratified(masked_mean, n_count, fv, sv, high, mono, strata)) \
                            if strata else (None, None, None)
                        ci = boots[s].stratified_ci(fv, sv, high, mono, strata) if strata else [None, None]
                        ci_b = boots[s].stratified_ci(fv, sv, high, mono, strata, alpha=0.05 / k_family) \
                            if strata else [None, None]
                    else:
                        ok = high.any() and mono.any()
                        est = interaction_samples(masked_mean, fv, sv, high, mono) if ok else None
                        dh = masked_mean(fv, high) - masked_mean(sv, high) if high.any() else None
                        dm = masked_mean(fv, mono) - masked_mean(sv, mono) if mono.any() else None
                        ci = boots[s].interaction_ci(fv, sv, high, mono)
                        ci_b = boots[s].interaction_ci(fv, sv, high, mono, alpha=0.05 / k_family)
                    n_h, n_m = int(high.sum()), int(mono.sum())
                    excl = ci[0] is not None and (ci[0] > 0 or ci[1] < 0)
                    rnd = lambda x: None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), 4)
                    res["interaction_tests"].append({
                        "model": model, "test_set": s, "scope": scope, "metric": metric, "strategy": st,
                        "n_high_cmi": n_h, "n_mono": n_m, "strata_high_mono": strata_note if scope == "stratified" else "",
                        "drop_high": rnd(dh), "drop_mono": rnd(dm), "diff": rnd(est),
                        "ci95_low": ci[0], "ci95_high": ci[1],
                        "ci_bonferroni_low": ci_b[0], "ci_bonferroni_high": ci_b[1],
                        "verdict": "inconclusive (bucket < 30 turns)" if min(n_h, n_m) < MIN_BUCKET
                        else ("differs" if excl else "inconclusive (CI crosses 0)")})

    # tokens by turn depth (held-out turns, mean over seeds)
    depth_sets = [POOLED] if POOLED in sets else [s for s in sets if s != "gold"] or sets
    idx = members[depth_sets[0]]
    depth = np.array([min(t["session_pos"] + 1, 10) for t in table])[idx]
    for model in models:
        for st in strategies:
            rs = [np.asarray(per_run[(model, st, sd)]["tokens_xlmr"], float)[idx] for sd in seeds
                  if (model, st, sd) in per_run]
            if rs:
                v = np.mean(rs, axis=0)
                res["token_growth"][f"{model}/{st}"] = {
                    "test_set": depth_sets[0],
                    "by_depth": {str(d): {"tokens": round(float(v[depth == d].mean()), 1), "n": int((depth == d).sum())}
                                 for d in sorted(set(depth.tolist()))}}
    return res


# ------------------------------------------------------------------ hypotheses
def find(rows, **kw):
    return [r for r in rows if all(r.get(k) == v for k, v in kw.items())]


def fmt_ci(lo, hi):
    return "n/a" if lo is None else f"[{lo:+.3f}, {hi:+.3f}]"


def verdicts(res, out_dir, ni_margin):
    tests, inter, metrics = res["stats_tests"], res["interaction_tests"], res["metrics"]
    sets = [s for s in res["settings"]["test_sets"] if s != "gold"]
    out = {}

    def overall(vs):
        if not vs:
            return "inconclusive (not run)"
        if all(v == "supported" for v in vs):
            return "supported"
        if all(v == "not supported" for v in vs):
            return "not supported"
        return "inconclusive (mixed)"

    # H1
    h1 = []
    for model in res["settings"]["models"]:
        for s in sets:
            rows = find(tests, model=model, test_set=s, metric="jga", reference=BASELINE)
            per = []
            for r in rows:
                if r["ci95_low"] is not None and r["ci95_low"] > 0 and r["p_holm"] < 0.05:
                    v = "supported"
                elif r["ci95_high"] is not None and r["ci95_high"] < 0 and r["p_holm"] < 0.05:
                    v = "not supported"
                else:
                    v = "inconclusive"
                per.append(v)
                h1.append({**r, "verdict": v})
            out[f"H1/{model}/{s}"] = overall(per)
    # H2
    h2 = []
    for model in res["settings"]["models"]:
        for s in sets:
            per = []
            full = metrics.get(f"{model}/{REFERENCE}/{s}")
            for st in H2_STRATEGIES:
                r = (find(tests, model=model, test_set=s, metric="jga", reference=REFERENCE, strategy=st) or [None])[0]
                m = metrics.get(f"{model}/{st}/{s}")
                if r is None or m is None or full is None:
                    continue
                fewer = m["tokens_xlmr_mean"][0] < full["tokens_xlmr_mean"][0]
                worse = r["diff"] < 0 and r["p_holm"] < 0.05
                if worse or not fewer:
                    v = "not supported"
                elif r["ci95_low"] is not None and r["ci95_low"] > -ni_margin:
                    v = "supported"
                else:
                    v = "inconclusive"
                saving = 1 - m["tokens_xlmr_mean"][0] / full["tokens_xlmr_mean"][0] if full["tokens_xlmr_mean"][0] else 0
                per.append(v)
                h2.append({**r, "token_saving": round(saving, 3), "verdict": v})
            out[f"H2/{model}/{s}"] = overall(per)
    # H3: headline = stratified by turn position; all turns pooled and follow-up only are reported next to it
    h3 = []
    for model in res["settings"]["models"]:
        for s in sets:
            for scope in H3_SCOPES:
                rows = find(inter, model=model, test_set=s, metric="jga", scope=scope)
                h3 += rows
                out[f"H3/{model}/{s}" + ("" if scope == "stratified" else f"/{scope}")] = (
                    "supported" if any(r["verdict"] == "differs" for r in rows)
                    else "inconclusive" if rows else "inconclusive (not run)")
    # H4 and scale: filled in by later stages
    h4 = _read_csv(os.path.join(out_dir, "robustness.csv"))
    bench = _read_csv(os.path.join(out_dir, "deployment_benchmark.csv"))
    return out, h1, h2, h3, h4, bench


def _read_csv(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_summary(res, path, out_dir, ni_margin):
    v, h1, h2, h3, h4, bench = verdicts(res, out_dir, ni_margin)
    v_sens, _, h2_sens, _, _, _ = verdicts(res, out_dir, H2_SENSITIVITY_MARGIN)
    sets = [s for s in res["settings"]["test_sets"] if s != "gold"]
    headline = POOLED if POOLED in sets else (sets[0] if sets else None)
    L = ["# Context strategies v2: hypothesis summary", "",
         f"Generated by `experiments/context_eval.py` on {time.strftime('%Y-%m-%d %H:%M')}. "
         f"Seeds: {res['settings']['seeds']}. Models: {', '.join(MODELS[m] for m in res['settings']['models'])}.", ""]
    if res["settings"]["fake_predictions"]:
        L += ["> **FAKE PREDICTIONS (dry run).** These numbers come from `tests/fixtures/fake_context_preds.py`, "
              "not from trained models. Do not report them.", ""]
    L += ["## Test sets", "", "| Set | Turns | Sessions | Switch turns | pure SI | pure EN | low CMI | high CMI | NE/OTHER only | CMI median (mixed) |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for s, t in res["turns"].items():
        b = t["cmi_buckets"]
        L.append(f"| {SET_LABEL[s]} | {t['n']} | {t['sessions']} | {t['switch_turns']} | " +
                 " | ".join(str(b.get(k, 0)) for k in CMI_BUCKETS) + f" | {res['settings']['cmi_median_threshold'][s]} |")
    L += ["", "Gold is the development set for the tracker rules, so it is reported separately and never decides a verdict. "
          f"Verdicts use the held-out sets; the headline is **{SET_LABEL.get(headline, headline)}**.", "",
          "## Decision rules", "",
          f"- p-values: exact McNemar on per-turn correctness (majority over seeds), Holm-corrected within each "
          f"model × test set × metric family. CIs: 95% cluster bootstrap over sessions ({B_RESAMPLES} resamples).",
          "- **H1** supported when every context strategy beats current_only on JGA (CI > 0 and Holm p < 0.05); "
          "not supported when every one is significantly worse; otherwise inconclusive.",
          f"- **H2** is a non-inferiority claim, so 'CI crosses 0' is the expected outcome, not a failure. A strategy is "
          f"supported when it uses fewer tokens than full_history, is not significantly worse (Holm p ≥ 0.05 or better), "
          f"and the CI lower bound of JGA(S) − JGA(full_history) is above −{ni_margin}; not supported when it is "
          f"significantly worse or not cheaper; otherwise inconclusive. Margin set with `--ni-margin`.",
          f"  A sensitivity row repeats the verdicts at a margin of {H2_SENSITIVITY_MARGIN}.",
          f"- **H3** supported when, for at least one reduced strategy, the difference in drop (high CMI − monolingual) "
          f"has a 95% CI that excludes 0 with ≥ {MIN_BUCKET} turns in both buckets; otherwise inconclusive "
          "(a bucket under 30 turns or a CI crossing 0). The CIs are not adjusted for the 6 strategies; the "
          "Bonferroni-adjusted CI is in `interaction_tests.csv`. Short follow-up answers are mostly monolingual and "
          "first requests mostly code-mixed, so turn position is confounded with code-mixing. The **headline is "
          "stratified by position**: the interaction is computed within first turns and within follow-up turns, "
          "combined weighted by the turns (high CMI + monolingual) in each, and its CI comes from resampling sessions "
          "with every turn keeping its stratum. All turns pooled and follow-up turns only are shown next to it.",
          "- Strategies marked *oracle (gold tags at test time) — upper bound* read the gold language/entity tags of "
          "earlier turns, which a deployed system does not have; their results are upper bounds.",
          "- An overall verdict mixes per-strategy verdicts: all supported → supported, all not supported → not "
          "supported, else inconclusive (mixed).", ""]

    def verdict_line(h, model):
        return " · ".join(f"{s}: **{v.get(f'{h}/{model}/{s}', 'n/a')}**" for s in sets)

    for h, title, rows, cols in [
        ("H1", "H1: current_only is worse than the context strategies (JGA)", h1,
         lambda r: f"| {name(r['strategy'])} | {r['acc_strategy']:.3f} | {r['acc_reference']:.3f} | {r['diff']:+.3f} | "
                   f"{fmt_ci(r['ci95_low'], r['ci95_high'])} | {r['p_holm']:.4f} | {r['verdict']} |"),
        ("H2", "H2: window / state / summary are not worse than full_history, at fewer tokens (JGA)", h2,
         lambda r: f"| {name(r['strategy'])} | {r['acc_strategy']:.3f} | {r['acc_reference']:.3f} | {r['diff']:+.3f} | "
                   f"{fmt_ci(r['ci95_low'], r['ci95_high'])} | {r['p_holm']:.4f} | {r['token_saving']:.0%} fewer | {r['verdict']} |"),
        ("H3", "H3: the drop from context reduction differs between high-CMI and monolingual turns (JGA)", h3,
         lambda r: f"| {name(r['strategy'])} | {r['scope'].replace('_', ' ')} | {r['n_high_cmi']} / {r['n_mono']} | "
                   f"{'n/a' if r['drop_high'] is None else format(r['drop_high'], '+.3f')} | "
                   f"{'n/a' if r['drop_mono'] is None else format(r['drop_mono'], '+.3f')} | "
                   f"{'n/a' if r['diff'] is None else format(r['diff'], '+.3f')} | {fmt_ci(r['ci95_low'], r['ci95_high'])} | {r['verdict']} |")]:
        L += [f"## {title}", ""]
        for model in res["settings"]["models"]:
            L += [f"**{MODELS[model]}**: {verdict_line(h, model)}", ""]
            if headline:
                hr = [r for r in rows if r["model"] == model and r["test_set"] == headline]
                if hr:
                    head = {"H1": "| strategy | JGA | JGA current_only | diff | 95% CI | Holm p | verdict |\n|---|---|---|---|---|---|---|",
                            "H2": "| strategy | JGA | JGA full_history | diff | 95% CI | Holm p | tokens | verdict |\n|---|---|---|---|---|---|---|---|",
                            "H3": "| strategy | turns | turns high / mono | drop high | drop mono | diff | 95% CI | verdict |\n|---|---|---|---|---|---|---|---|"}[h]
                    L += [f"{SET_LABEL[headline]}:", "", head] + [cols(r) for r in hr] + [""]
            if h == "H2":
                sens = " · ".join(f"{s}: **{v_sens.get(f'H2/{model}/{s}', 'n/a')}**" for s in sets)
                L += [f"Sensitivity, margin {H2_SENSITIVITY_MARGIN}: {sens}", ""]
                sr = [r for r in h2_sens if r["model"] == model and r["test_set"] == headline]
                if sr:
                    main_v = {r["strategy"]: r["verdict"] for r in h2 if r["model"] == model and r["test_set"] == headline}
                    L += [f"| strategy | CI low | verdict at margin {ni_margin} | verdict at margin {H2_SENSITIVITY_MARGIN} |",
                          "|---|---|---|---|"] + [
                        f"| {name(r['strategy'])} | {fmt_ci(r['ci95_low'], r['ci95_high'])} | {main_v.get(r['strategy'])} | "
                        f"{r['verdict']} |" for r in sr] + [""]
            if h == "H3":
                for scope in H3_SCOPES[1:]:
                    line = " · ".join(f"{s}: **{v.get(f'H3/{model}/{s}/{scope}', 'n/a')}**" for s in sets)
                    L += [f"{scope.replace('_', ' ').capitalize()}: {line}", ""]
                if any(v.get(f"H3/{model}/{s}") != v.get(f"H3/{model}/{s}/all_turns") for s in sets):
                    L += ["> The stratified and all-turns verdicts disagree: part of the all-turns effect comes from turn "
                          "position (short monolingual answers vs code-mixed first requests), not from code-mixing.", ""]
    L += ["## H4: the hybrid tracker (rules + XLM-R NER) degrades less than rules only on messy input", ""]
    if h4:
        L += _h4_lines(h4)
    else:
        L += ["**inconclusive (not run yet)**: `robustness.csv` is written by `experiments/perturb.py` (Stage 3).", ""]
    L += ["## Scale claim: cheap and fast enough on CPU", ""]
    if bench:
        L += _bench_lines(bench)
    else:
        L += ["**inconclusive (not run yet)**: `deployment_benchmark.csv` is written by `experiments/bench_cpu.py` (Stage 4). "
              "Tokens per turn from the predictions:", ""]
    L += ["| strategy | XLM-R tokens/turn (mean) | cl100k tokens/turn | XLM-R latency (ms, notebook device) |", "|---|---|---|---|"]
    for st in res["settings"]["strategies"]:
        m = res["metrics"].get(f"xlmr/{st}/{headline}") or {}
        if m:
            L.append(f"| {name(st)} | {m['tokens_xlmr_mean'][0]:.1f} | {m['tokens_cl100k_mean'][0]:.1f} | "
                     f"{m['latency_ms_mean'][0]:.1f} ({m.get('device')}) |")
    L += ["", "## Gold (development set, reported separately)", "",
          "| model | strategy | JGA (mean ± std) | intent acc | 95% CI JGA |", "|---|---|---|---|---|"]
    for k, m in res["metrics"].items():
        if m["test_set"] == "gold":
            L.append(f"| {MODELS[m['model']]} | {name(m['strategy'])} | {m['jga'][0]:.3f} ± {m['jga'][1]:.3f} | "
                     f"{m['intent_acc'][0]:.3f} | {fmt_ci(*m['jga_ci95'])} |")
    L += ["", "## Caveats", "",
          f"- {name('keyword_summary')} and {name('structured_state')}: they read gold language/entity tags; "
          "summary reads only the text.",
          "- Sessions are stitched from 2–4 short dialogues; gold slot states restart with each dialogue, so the "
          "tracker is reset there and JGA measures within-dialogue slot tracking with the strategy's intent.",
          "- Synthetic language tags (for CMI) are LLM-written (897 turns) or hand-checked (80), not fully gold.",
          "- Fresh is small (50 turns): most of its CMI buckets are under 30 turns.",
          "- Latency in the predictions was measured on the notebook's device; the CPU numbers come from bench_cpu.py.", ""]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))


def _h4_lines(rows):
    """Stage 3 writes robustness.csv; summarised here so summary.md has all hypotheses."""
    L = ["| test set | perturbation | rules JGA | hybrid JGA | rules drop | hybrid drop | valid |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r.get('test_set')} | {r.get('perturbation')} | {r.get('rules_jga')} | {r.get('hybrid_jga')} | "
                 f"{r.get('rules_drop')} | {r.get('hybrid_drop')} | {r.get('valid')} |")
    verdict = next((r.get("h4_verdict") for r in rows if r.get("h4_verdict")), None)
    return [f"**{verdict or 'see table'}**", ""] + L + [""]


def _bench_lines(rows):
    L = ["| strategy | p50 ms | p95 ms | turns/s | peak MB | tokens/conversation |", "|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r.get('strategy')} | {r.get('latency_p50_ms')} | {r.get('latency_p95_ms')} | "
                 f"{r.get('throughput_turns_per_s')} | {r.get('peak_memory_mb')} | {r.get('tokens_per_conversation')} |")
    verdict = next((r.get("scale_verdict") for r in rows if r.get("scale_verdict")), None)
    return [f"**{verdict or 'see table'}**", ""] + L + [""]


# ------------------------------------------------------------------ outputs
def write_csv(path, rows):
    if not rows:
        open(path, "w").close()
        return
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


INK, INK2, GRID = "#0b0b0b", "#52514e", "#e5e5e5"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
MODEL_COLOUR = {"xlmr": SERIES[0], "tfidf": SERIES[1]}


def _style(plt):
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": "#888", "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                         "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
                         "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb", "savefig.facecolor": "#fcfcfb"})


def plot_all(res, out_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _style(plt)
    models, strategies = res["settings"]["models"], res["settings"]["strategies"]
    sets = [s for s in ("synthetic", "fresh", "gold") if s in res["settings"]["test_sets"]]
    fake = " (FAKE dry-run data)" if res["settings"]["fake_predictions"] else ""

    # 1. Pareto: JGA vs tokens, one panel per test set, gold labelled as dev
    fig, axes = plt.subplots(1, len(sets), figsize=(4.6 * len(sets), 4.4), squeeze=False)
    for ax, s in zip(axes[0], sets):
        for model in models:
            pts = [(res["metrics"][k]["tokens_xlmr_mean"][0], *res["metrics"][k]["jga"], st)
                   for st in strategies for k in [f"{model}/{st}/{s}"] if k in res["metrics"]]
            ax.errorbar([p[0] for p in pts], [p[1] for p in pts], yerr=[p[2] for p in pts], fmt="o", ms=7, capsize=3,
                        lw=1.2, color=MODEL_COLOUR[model], markeredgecolor="#fcfcfb", markeredgewidth=1.5,
                        label=MODELS[model], zorder=3)
            front, best = [], -1                    # Pareto front: no other point has fewer tokens and higher JGA
            for p in sorted(pts):
                if p[1] > best:
                    front.append(p); best = p[1]
            ax.plot([p[0] for p in front], [p[1] for p in front], color=MODEL_COLOUR[model], lw=1, ls="--", alpha=0.6, zorder=2)
            if model == "xlmr":             # labels alternate above/below, pushed further when points are close
                for i, p in enumerate(sorted(pts)):
                    close = i > 0 and abs(p[0] - sorted(pts)[i - 1][0]) < 0.04 * max(q[0] for q in pts)
                    dy = (7 if i % 2 == 0 else -12) * (2 if close else 1)
                    ax.annotate(p[3].replace("_", " "), (p[0], p[1]), textcoords="offset points",
                                xytext=(6, dy), fontsize=7.5, color=INK2)
        ax.set_title(SET_LABEL[s] + (" — dev" if s == "gold" else ""), loc="left", fontsize=10, color=INK)
        ax.set_xlabel("Input tokens per turn (mean, XLM-R tokenizer)")
        ax.set_ylabel("Joint goal accuracy (mean ± std over seeds)")
    axes[0][0].legend(frameon=False, loc="lower right")
    fig.suptitle("JGA vs context cost; dashed = Pareto front" + fake, x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "pareto_jga_vs_tokens.png"), dpi=200)
    plt.close(fig)

    # 2. token growth by turn depth
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    model = "xlmr" if "xlmr" in models else models[0]
    ends = []
    for colour, st in zip(SERIES, strategies):
        g = res["token_growth"].get(f"{model}/{st}")
        if not g:
            continue
        ds = sorted(g["by_depth"], key=int)
        ys = [g["by_depth"][d]["tokens"] for d in ds]
        ax.plot([int(d) for d in ds], ys, color=colour, lw=2, marker="o", ms=4, label=st.replace("_", " "))
        ends.append((ys[-1], int(ds[-1]), st))
    gap, last = 0.045 * max((e[0] for e in ends), default=1), None     # end labels at least `gap` apart
    for y, x, st in sorted(ends):
        last = y if last is None else max(y, last + gap)
        ax.annotate(st.replace("_", " "), (x, y), xytext=(x + 0.12, last), textcoords="data",
                    fontsize=7.5, color=INK2, va="center")
    ax.axhline(128, color="#888", lw=1, ls="--")
    ax.text(0.01, 130, "model limit (128 tokens)", fontsize=7.5, color=INK2, transform=ax.get_yaxis_transform())
    ax.set_xticks(range(1, 11)); ax.set_xticklabels([str(i) for i in range(1, 10)] + ["10+"])
    ax.set_xlabel("User turn number in the session")
    ax.set_ylabel("Input tokens (mean, XLM-R tokenizer)")
    any_g = next(iter(res["token_growth"].values()), {})
    ax.set_title(f"Tokens per turn by depth — {SET_LABEL.get(any_g.get('test_set'), '')}" + fake,
                 loc="left", fontsize=10, color=INK)
    ax.legend(frameon=False, fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=4)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "token_growth_by_turn_depth.png"), dpi=200)
    plt.close(fig)

    # 3. CMI breakdown: JGA per strategy and CMI bucket (XLM-R, headline set)
    head = POOLED if POOLED in res["settings"]["test_sets"] else (sets[0] if sets else None)
    bks = [b for b in CMI_BUCKETS[:4] if res["turns"].get(head, {}).get("cmi_buckets", {}).get(b)]
    fig, axes = plt.subplots(1, len(models), figsize=(6.2 * len(models), 4.4), squeeze=False)
    width = 0.8 / max(1, len(bks))
    for ax, model in zip(axes[0], models):
        for j, (b, colour) in enumerate(zip(bks, SERIES)):
            rows = {r["strategy"]: r for r in res["cmi_breakdown"] if r["model"] == model and r["test_set"] == head
                    and r["bucket_type"] == "cmi" and r["bucket"] == b}
            xs = [i + (j - (len(bks) - 1) / 2) * width for i in range(len(strategies))]
            ax.bar(xs, [rows[s]["jga_mean"] if s in rows else 0 for s in strategies], width * 0.92,
                   yerr=[rows[s]["jga_std"] if s in rows else 0 for s in strategies], color=colour, capsize=2,
                   error_kw={"lw": 0.8, "ecolor": INK2}, label=f"{b.replace('_', ' ')} (n={res['turns'][head]['cmi_buckets'][b]})")
        ax.set_xticks(range(len(strategies)))
        ax.set_xticklabels([s.replace("_", "\n") for s in strategies], fontsize=7.5)
        ax.set_ylim(0, 1.05)
        ax.set_ylabel("JGA (mean ± std over seeds)")
        ax.set_title(f"{MODELS[model]}", loc="left", fontsize=10, color=INK)
        ax.grid(axis="x", visible=False)
    axes[0][0].legend(frameon=False, fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=4)
    fig.suptitle(f"JGA by code-mixing bucket — {SET_LABEL.get(head, head)}; CMI threshold "
                 f"{res['settings']['cmi_median_threshold'].get(head)}" + fake, x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "cmi_breakdown.png"), dpi=200)
    plt.close(fig)

    # 4. interaction forest plot
    iset = [s for s in ("synthetic", "fresh", POOLED) if s in res["settings"]["test_sets"]] or sets
    reduced = [s for s in strategies if s != REFERENCE]
    fig, axes = plt.subplots(1, len(iset), figsize=(4.2 * len(iset), 0.45 * len(reduced) + 1.8), squeeze=False, sharey=True)
    for ax, s in zip(axes[0], iset):
        series = [(m, sc) for m in models for sc in H3_SCOPES]
        for k, (model, scope) in enumerate(series):
            rows = {r["strategy"]: r for r in res["interaction_tests"] if r["model"] == model and r["test_set"] == s
                    and r["metric"] == "jga" and r["scope"] == scope}
            filled = scope == "stratified"           # the headline; the other two hollow (square = follow-up only)
            for i, st in enumerate(reduced):
                r = rows.get(st)
                if not r or r["diff"] is None:
                    continue
                y = i + (k - (len(series) - 1) / 2) * 0.13
                if r["ci95_low"] is not None:
                    ax.plot([r["ci95_low"], r["ci95_high"]], [y, y], color=MODEL_COLOUR[model], lw=2 if filled else 1.1,
                            solid_capstyle="round")
                ax.plot([r["diff"]], [y], "s" if scope == "follow_up" else "o", ms=5.5,
                        color=MODEL_COLOUR[model] if filled else "#fcfcfb",
                        markeredgecolor=MODEL_COLOUR[model] if not filled else "#fcfcfb", markeredgewidth=1.4,
                        label=f"{MODELS[model]}, {scope.replace('_', ' ')}" if i == 0 else None)
        ax.axvline(0, color="#888", lw=1)
        ax.set_yticks(range(len(reduced))); ax.set_yticklabels([st.replace("_", " ") for st in reduced])
        ax.invert_yaxis()
        t = res["turns"][s]["cmi_buckets"]
        ax.set_title(f"{SET_LABEL[s]}\nhigh CMI n={t.get('high_cmi', 0)}, mono n={t.get('pure_si', 0) + t.get('pure_en', 0)}",
                     loc="left", fontsize=9, color=INK)
        ax.set_xlabel("drop(high CMI) − drop(mono), JGA")
        ax.grid(axis="y", visible=False)
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=8, loc="lower center", ncol=6)
    fig.suptitle("H3: does reducing context hurt code-mixed turns more? (95% cluster-bootstrap CI; n = all turns; filled = stratified)" + fake,
                 x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(os.path.join(out_dir, "interaction_tests.png"), dpi=200)
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--preds-dir", default="results/context_v2/preds")
    ap.add_argument("--out-dir", default="results/context_v2")
    ap.add_argument("--test-set", choices=["gold", "synthetic", "fresh", "all"], default="all")
    ap.add_argument("--ni-margin", type=float, default=0.05, help="H2 non-inferiority margin on JGA")
    ap.add_argument("--overwrite", action="store_true", help="replace results already in --out-dir")
    ap.add_argument("--no-plots", action="store_true")
    a = ap.parse_args(argv)

    os.makedirs(a.out_dir, exist_ok=True)
    existing = [f for f in OUTPUTS if os.path.exists(os.path.join(a.out_dir, f))]
    if existing and not a.overwrite:
        sys.exit(f"{a.out_dir} already has {existing}; choose another --out-dir or pass --overwrite")
    test_sets = ["gold", "synthetic", "fresh"] if a.test_set == "all" else [a.test_set]
    t0 = time.time()
    runs = load_preds(a.preds_dir)
    print(f"{len(runs)} runs from {a.preds_dir}: models {sorted({k[0] for k in runs})}, "
          f"strategies {len({k[1] for k in runs})}, seeds {sorted({k[2] for k in runs})}")
    states, tokens = load_reference(test_sets)
    table = turn_table(runs, test_sets, tokens)
    res = analyse(runs, table, states, a.ni_margin)
    res["settings"]["run_at"] = time.strftime("%Y-%m-%d %H:%M")
    res["settings"]["preds_dir"] = a.preds_dir

    with open(os.path.join(a.out_dir, "context_jga_results.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=2)
    write_csv(os.path.join(a.out_dir, "stats_tests.csv"), res["stats_tests"])
    write_csv(os.path.join(a.out_dir, "cmi_breakdown.csv"), res["cmi_breakdown"])
    write_csv(os.path.join(a.out_dir, "interaction_tests.csv"), res["interaction_tests"])
    write_summary(res, os.path.join(a.out_dir, "summary.md"), a.out_dir, a.ni_margin)
    if not a.no_plots:
        plot_all(res, a.out_dir)

    print(f"\n{'model':7s}{'strategy':18s}" + "".join(f"{s:>22s}" for s in res["settings"]["test_sets"]))
    for model in res["settings"]["models"]:
        for st in res["settings"]["strategies"]:
            cells = [res["metrics"].get(f"{model}/{st}/{s}") for s in res["settings"]["test_sets"]]
            print(f"{model:7s}{st:18s}" + "".join(f"{'-':>22s}" if c is None else
                                                  f"{c['jga'][0]:>10.3f}±{c['jga'][1]:.3f} ({c['tokens_xlmr_mean'][0]:>4.0f}t)"
                                                  for c in cells))
    v = verdicts(res, a.out_dir, a.ni_margin)[0]
    print("\nverdicts:", json.dumps(v, indent=1))
    written = [f for f in OUTPUTS if os.path.exists(os.path.join(a.out_dir, f))]
    print(f"\nwrote {len(written)} files to {a.out_dir} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
