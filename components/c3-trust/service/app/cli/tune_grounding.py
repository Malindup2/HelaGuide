"""
Find good grounding thresholds for YOUR embedding model, using the labelled mock messages.

    python -m app.cli.tune_grounding            (real model; run after check_model works)

It scores every labelled message once, then tries many combinations of
  C3_TAU_F         minimum fact score
  C3_DELTA_F       minimum lead over the runner-up fact (bigger = asks the citizen more often)
  C3_TAU_MISS_COS  below this document-phrase similarity a document is treated as "not in the graph"
and prints the best ones as lines you can paste into service/.env.

HOW THE CHOICE IS MADE (so the test result stays honest):
  * settings are ranked ONLY by accuracy on the "tune" messages;
  * many settings usually tie. From the tied ones it picks the most cautious margin (largest C3_DELTA_F) and then
    the middle of the tied range for the other two, because the middle of a plateau is the most robust;
  * the "test" messages are never used to choose. Their accuracy is reported afterwards, and that is the number to quote.
"""
import argparse
import itertools

from app.cli._common import add_common_args, banner, settings_from_args, table, utf8
from app.core.evaluate import accuracy_by, load_dataset, run_grounding
from app.core.pipeline import Pipeline

TAU_F = [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]
DELTA_F = [0.02, 0.04, 0.06, 0.08, 0.10]
TAU_MISS = [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]


def score(rows, split):
    sel = [r for r in rows if r["label"]["split"] == split]
    return (sum(r["ok"] for r in sel) / len(sel)) if sel else 0.0


def middle(values):
    vals = sorted(set(values))
    return vals[len(vals) // 2]


def choose(combos):
    """combos: (tune_acc, test_acc, tau_f, delta_f, miss). Uses tune accuracy only."""
    best = max(c[0] for c in combos)
    ties = [c for c in combos if c[0] == best]
    delta = max(c[3] for c in ties)                         # the most cautious margin that is just as accurate
    ties = [c for c in ties if c[3] == delta]
    want_f, want_m = middle(c[2] for c in ties), middle(c[4] for c in ties)
    pick = min(ties, key=lambda c: abs(c[2] - want_f) + abs(c[4] - want_m))
    return pick, len([c for c in combos if c[0] == best])


def main(argv=None) -> None:
    utf8()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(ap)
    ap.add_argument("--top", type=int, default=8)
    args = ap.parse_args(argv)
    s = settings_from_args(args)
    s = s.model_copy(update={"database_url": "sqlite://"})      # tuning never needs PostgreSQL
    pipe = Pipeline.build(s, reset=True)
    pipe.sync_facts()
    ds = load_dataset(s.data_dir)
    banner(f"Tuning grounding thresholds ({pipe.embedder.name})")
    combos = []
    for tau_f, delta_f, miss in itertools.product(TAU_F, DELTA_F, TAU_MISS):
        pipe.grounding.s = s.model_copy(update={"tau_f": tau_f, "delta_f": delta_f, "tau_miss_cos": miss})
        rows = run_grounding(pipe, ds)
        combos.append((score(rows, "tune"), score(rows, "test"), tau_f, delta_f, miss))
    pick, n_ties = choose(combos)
    shown = sorted(combos, key=lambda c: (-c[0], -c[3], abs(c[2] - pick[2]) + abs(c[4] - pick[4])))[: args.top]
    print(table(["tune acc", "test acc", "C3_TAU_F", "C3_DELTA_F", "C3_TAU_MISS_COS"],
                [[f"{a:.0%}", f"{b:.0%}", f, d, m] for a, b, f, d, m in shown]))
    print(f"\n{n_ties} of {len(combos)} settings reach the best tune accuracy ({pick[0]:.0%}).")
    print("Chosen: the most cautious margin among them, and the middle of the tied range for the other two.")
    print("\nPaste these into service/.env :")
    print(f"C3_TAU_F={pick[2]}\nC3_DELTA_F={pick[3]}\nC3_TAU_MISS_COS={pick[4]}")
    pipe.grounding.s = s.model_copy(update={"tau_f": pick[2], "delta_f": pick[3], "tau_miss_cos": pick[4]})
    rows = run_grounding(pipe, ds)
    banner("Accuracy with the chosen thresholds (the test messages were NOT used to choose)", "-")
    for key in ("style", "path", "split"):
        print(f"by {key:6}: " + ", ".join(f"{k} {a}/{n}" for k, (a, n) in accuracy_by(rows, key).items()))
    good = sum(r["ok"] for r in rows)
    print(f"overall : {good}/{len(rows)} ({good / len(rows):.0%})")
    docs = [r for r in rows if r["result"].trace.get("phrase_similarity") is not None]
    if docs:
        banner("Document messages: why each was kept or reported as 'not in the graph'", "-")
        print(table(["message", "expected", "phrase similarity", "shared distinctive words", "decision", "ok"],
                    [[r["label"]["message_id"], r["label"]["expected_state"], r["result"].trace["phrase_similarity"],
                      ", ".join(r["result"].trace.get("shared_words") or []) or "none", r["result"].state,
                      "yes" if r["ok"] else "NO"] for r in docs]))
    fails = [r for r in rows if not r["ok"]]
    if fails:
        banner("Messages still wrong (this is your failure analysis)", "-")
        for r in fails:
            g = r["result"]
            top = (g.trace.get("fact_candidates") or [{}])[0]
            extra = f" document-phrase-similarity={g.trace['phrase_similarity']}" if g.trace.get("phrase_similarity") is not None else ""
            print(f"{r['label']['message_id']:7} expected {r['label']['expected_state']}/{r['label']['expected_fact_id']}"
                  f"\n        got {g.state}/{g.fact_id} reason={g.reason} best={top.get('fact_id')} score={top.get('score')} cos={top.get('cos')}{extra}")


if __name__ == "__main__":
    main()
