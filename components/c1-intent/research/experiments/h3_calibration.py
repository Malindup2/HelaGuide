"""
H3 calibration: how often does each H3 method say "supported" when there is no code-mixing effect?

Runs the H3 tests of context_eval.py on many null data sets from tests/fixtures/fake_context_preds.py. The fake
error rate depends on strategy, model and turn position (first / follow-up) only, so:
  - intent accuracy is an exact null for every position-aware method (permutation, stratified, follow-up only);
    "all turns" pools the positions, so it is expected to fire (that is the confound it cannot remove);
  - JGA is only an approximate null: the rule tracker may fill slots worse on code-mixed text, and a wrong
    intent costs no JGA on a turn whose slots already failed, so a small real JGA interaction can exist.
The test turns, sessions, CMI buckets, bootstrap resamples and permutations are the real ones.

Run from research/ (CPU; about 10-20 minutes with 14 processes):
    python experiments/h3_calibration.py --n 200 --out-dir results/context_v2
Writes h3_calibration.csv and h3_calibration.json (never overwrites without --overwrite).
"""
import argparse
import collections
import json
import multiprocessing as mp
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tests"))
import context_eval as ce  # noqa: E402

SETS = ["synthetic", "fresh", ce.POOLED]
METRICS = (("intent_acc", "intent_ok"), ("jga", "jga_ok"))
_W = {}                                  # per-process state


def _init():
    from fixtures.fake_context_preds import bot_text, fake_runs, test_sessions
    sessions, bot = test_sessions(), bot_text()
    first = fake_runs(seeds=(1,), strategies=["full_history"], models=("xlmr",), with_inputs=False,
                      sets=sessions, bot=bot)
    test_sets = ["synthetic", "fresh"]
    states, tokens = ce.load_reference(test_sets)
    table = ce.turn_table(first, test_sets, tokens)
    members, _, buckets, boots, perms = ce.prepare(table, SETS)
    _W.update(fake_runs=fake_runs, sessions=sessions, bot=bot, states=states, table=table, members=members,
              buckets=buckets, boots=boots, perms=perms, memo={})


def _one(noise_seed, scopes=None, metrics=METRICS):
    if not _W:
        _init()
    w = _W
    runs = w["fake_runs"](noise_seed=noise_seed, with_inputs=False, sets=w["sessions"], bot=w["bot"])
    runs = {k: [r for r in v if r["test_set"] in ("synthetic", "fresh")] for k, v in runs.items()}
    if all(key == "intent_ok" for _, key in metrics):        # intent only: no need to run the slot tracker
        order = [(t["test_set"], t["session_id"], t["session_pos"]) for t in w["table"]]
        per_run = {}
        for k, v in runs.items():
            ok = {(r["test_set"], r["session_id"], r["session_pos"]): r["pred_intent"] == r["gold_intent"] for r in v}
            per_run[k] = {"intent_ok": [ok[o] for o in order]}
    else:
        per_run = {k: ce.eval_run(v, w["table"], w["states"], memo=w["memo"]) for k, v in runs.items()}
    vec = ce.make_vec(per_run, sorted({k[2] for k in runs}), w["members"])
    rows = ce.h3_rows(vec, list(ce.MODELS), ce.STRATEGIES, SETS, w["table"], w["members"], w["buckets"], w["boots"],
                      w["perms"], metrics=metrics, scopes=scopes)
    out = []
    for r in rows:
        if r["scope"] == "permutation":
            raw = r["p_perm"] is not None and r["p_perm"] < 0.05
            adj = r["p_holm"] is not None and r["p_holm"] < 0.05
        else:
            raw = r["ci95_low"] is not None and (r["ci95_low"] > 0 or r["ci95_high"] < 0)
            adj = r["ci_bonferroni_low"] is not None and (r["ci_bonferroni_low"] > 0 or r["ci_bonferroni_high"] < 0)
        out.append((r["scope"], r["metric"], r["test_set"], r["model"], r["strategy"], r["verdict"] == "differs",
                    raw, adj, min(r["n_high_cmi"], r["n_mono"]) >= ce.MIN_BUCKET))
    return noise_seed, out


def summarise(results):
    """Rates per method x metric x test set. A family = the 6 reduced strategies of one model."""
    fam = collections.defaultdict(lambda: collections.defaultdict(list))
    comp = collections.defaultdict(lambda: collections.defaultdict(list))
    eligible = {}
    for seed, rows in results:
        by_family = collections.defaultdict(list)
        for scope, metric, ts, model, st, supported, raw, adj, ok in rows:
            by_family[(scope, metric, ts, model)].append((supported, raw, adj))
            comp[(scope, metric, ts)]["raw"].append(raw)
            eligible[(scope, metric, ts)] = ok
        for (scope, metric, ts, model), v in by_family.items():
            fam[(scope, metric, ts)]["supported"].append(any(x[0] for x in v))
            fam[(scope, metric, ts)]["any_raw"].append(any(x[1] for x in v))
            fam[(scope, metric, ts)]["any_adjusted"].append(any(x[2] for x in v))
    table = []
    for key in sorted(fam, key=lambda k: (ce.H3_SCOPES.index(k[0]), k[1] != "intent_acc", SETS.index(k[2]))):
        scope, metric, ts = key
        f, c = fam[key], comp[key]
        table.append({"method": scope, "metric": metric, "test_set": ts, "families": len(f["supported"]),
                      "says_supported": round(float(np.mean(f["supported"])), 4),
                      "family_any_adjusted": round(float(np.mean(f["any_adjusted"])), 4),
                      "family_any_unadjusted": round(float(np.mean(f["any_raw"])), 4),
                      "per_comparison_unadjusted": round(float(np.mean(c["raw"])), 4),
                      "buckets_eligible": eligible[key],
                      "null": "exact" if metric == "intent_acc" and scope != "all_turns" else
                      ("not null (turn position)" if scope == "all_turns" else "approximate (slot errors)")})
    return table


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--n", type=int, default=200, help="number of null data sets")
    ap.add_argument("--out-dir", default="results/context_v2")
    ap.add_argument("--processes", type=int, default=max(1, min(14, (os.cpu_count() or 2) - 2)))
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args(argv)
    os.makedirs(a.out_dir, exist_ok=True)
    paths = [os.path.join(a.out_dir, f) for f in ("h3_calibration.csv", "h3_calibration.json")]
    if any(os.path.exists(p) for p in paths) and not a.overwrite:
        sys.exit(f"{a.out_dir} already has h3_calibration.*; pass --overwrite")
    t0 = time.time()
    seeds = list(range(1, a.n + 1))
    if a.processes > 1:
        with mp.Pool(a.processes) as pool:
            results = []
            for i, r in enumerate(pool.imap_unordered(_one, seeds, chunksize=2), 1):
                results.append(r)
                if i % 20 == 0:
                    print(f"  {i}/{a.n} null data sets ({time.time() - t0:.0f}s)", flush=True)
    else:
        results = [_one(s) for s in seeds]
    table = summarise(sorted(results))
    ce.write_csv(paths[0], table)
    with open(paths[1], "w", encoding="utf-8") as fh:
        json.dump({"run_at": time.strftime("%Y-%m-%d %H:%M"), "null_data_sets": a.n,
                   "permutations": ce.N_PERMUTATIONS, "bootstrap_resamples": ce.B_RESAMPLES,
                   "definitions": {
                       "says_supported": "share of families (model x test set, 6 strategies) where the H3 verdict rule "
                                         "says supported (incl. the 30-turn bucket rule)",
                       "family_any_adjusted": "same without the bucket rule, with Holm (permutation) or Bonferroni "
                                              "(bootstrap CIs) across the 6 strategies",
                       "family_any_unadjusted": "same, unadjusted 95%",
                       "per_comparison_unadjusted": "share of single strategy comparisons significant at 95%"},
                   "rates": table}, fh, indent=2)
    print(f"\n{'method':12s}{'metric':12s}{'set':11s}{'says supp.':>11s}{'fam adj':>9s}{'fam raw':>9s}{'per comp':>9s}  null")
    for r in table:
        print(f"{r['method']:12s}{r['metric']:12s}{r['test_set']:11s}{r['says_supported']:>11.3f}"
              f"{r['family_any_adjusted']:>9.3f}{r['family_any_unadjusted']:>9.3f}{r['per_comparison_unadjusted']:>9.3f}"
              f"  {r['null']}{'' if r['buckets_eligible'] else ' (buckets < 30: never supported)'}")
    print(f"\nwrote {paths[0]} and {paths[1]} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
