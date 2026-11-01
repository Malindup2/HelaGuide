"""
Chooses the hint gate C1_HINT_MIN_CONFIDENCE for the LLM dialogue evaluation (dialogue_eval.py), on the gold
dialogues, before any run on the fresh set. No LLM calls.

In hybrid mode the LLM gets XLM-R's intent as a hint. Below the gate that hint is marked "weak". Marking a hint weak
helps on a turn where XLM-R is wrong and only costs on a turn where it is right, so for each gate g on a fixed grid:

    net(g) = (turns with confidence < g where XLM-R is wrong) - (turns with confidence < g where it is right)

and the chosen gate is the g with the largest net (ties: the lower g). If no g has a positive net, the gate is 0.0
(gating off). The grid is fixed in advance: GRID below.

Data: the gold dialogues (data/seed_all.json, 142 user turns). Not the synthetic set: the intent head of the
deployed model (run_v2_seed1) was trained on the synthetic silver set (Observation 10), so its confidence there is
inflated.
The gold set was used to write the rules, but the gate depends only on XLM-R's confidence, so that does not bias it.
XLM-R's input is built as in the service (engine.Session): the last 3 user messages, greetings left out; greeting
turns get no prediction and are not counted. The gate catches unsure errors only, not confident ones (in the rigid
log XLM-R said unsupported_service at 0.61 and 0.72).

Also printed: how many fresh turns fall below the chosen gate (a count only; fresh accuracy is not looked at).

Run from research/ (CPU, about a minute):
    python experiments/gate_calibration.py --model-dir models/c1/run_v2_seed1
Writes results/gate_calibration.json.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from c1_dst import is_greeting  # noqa: E402
from dst_eval import load_json, user_turns  # noqa: E402

GRID = (0.35, 0.4, 0.5, 0.6, 0.7, 0.8)
BINS = (0.0, 0.35, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0001)


def predictions(dialogues, classify):
    """[{"id", "gold", "pred", "confidence"}] for every non-greeting user turn. classify(history) -> (intent, conf)."""
    out = []
    for d in dialogues:
        history = []
        for ti, text, gold, _ in user_turns(d):
            if is_greeting(text):
                continue
            history.append(text)
            intent, conf = classify(history)
            out.append({"id": f"{d['dialogue_id']}/{ti}", "gold": gold.get("intent"), "pred": intent,
                        "confidence": conf})
    return out


def gate_table(rows, grid=GRID):
    """For each gate: turns below it, how many of those XLM-R got wrong / right, and net = wrong - right."""
    table = []
    for g in grid:
        below = [r for r in rows if r["confidence"] < g]
        wrong = sum(r["pred"] != r["gold"] for r in below)
        table.append({"gate": g, "below": len(below), "wrong_below": wrong, "right_below": len(below) - wrong,
                      "net": 2 * wrong - len(below)})
    return table


def choose_gate(table):
    """The gate with the largest net (ties: the lower gate); 0.0 when no gate has a positive net."""
    best = max(table, key=lambda t: (t["net"], -t["gate"]))
    return best["gate"] if best["net"] > 0 else 0.0


def reliability(rows, bins=BINS):
    """XLM-R accuracy per confidence bin [lo, hi)."""
    out = []
    for lo, hi in zip(bins, bins[1:]):
        inside = [r for r in rows if lo <= r["confidence"] < hi]
        out.append({"bin": f"[{lo:.2f}, {min(hi, 1.0):.2f}{']' if hi > 1 else ')'}", "n": len(inside),
                    "accuracy": round(sum(r["pred"] == r["gold"] for r in inside) / len(inside), 3) if inside else None})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--model-dir", default="models/c1/run_v2_seed1", help="the deployed C1 model folder")
    ap.add_argument("--gold", default="data/seed_all.json")
    ap.add_argument("--fresh", default="data/fresh_dialogues_states.json", help="for the count below the gate only")
    ap.add_argument("--out", default="results/gate_calibration.json")
    a = ap.parse_args()

    from c1_engine import C1Engine      # torch and transformers: only when actually run
    engine = C1Engine(a.model_dir)
    gold = load_json(a.gold)
    rows = predictions(gold, engine.classify_intent)
    table = gate_table(rows)
    gate = choose_gate(table)
    fresh_rows = predictions(load_json(a.fresh), engine.classify_intent) if os.path.exists(a.fresh) else []
    fresh_below = sum(r["confidence"] < gate for r in fresh_rows)

    acc = sum(r["pred"] == r["gold"] for r in rows) / len(rows)
    print(f"gold: {len(rows)} turns with an XLM-R prediction ({sum(len(user_turns(d)) for d in gold) - len(rows)} "
          f"greeting turns left out), XLM-R accuracy {acc:.3f}")
    print("\nreliability (gold)")
    for b in reliability(rows):
        print(f"  {b['bin']:<14} n={b['n']:<4} accuracy {b['accuracy']}")
    print("\ngate grid (gold): marking a hint weak helps when XLM-R is wrong, costs when it is right")
    print(f"  {'gate':>5} {'below':>6} {'wrong':>6} {'right':>6} {'net':>5}")
    for t in table:
        print(f"  {t['gate']:>5} {t['below']:>6} {t['wrong_below']:>6} {t['right_below']:>6} {t['net']:>5}")
    print(f"\nchosen gate: {gate}" + ("  (no gate has a positive net: gating off)" if gate == 0.0 else ""))
    if fresh_rows:
        print(f"fresh turns below it: {fresh_below} of {len(fresh_rows)} (count only)")

    result = {"run_at": time.strftime("%Y-%m-%d %H:%M"), "model_dir": a.model_dir, "data": a.gold, "grid": list(GRID),
              "rule": "max over the grid of (wrong - right) among turns below the gate; ties: lower gate; "
                      "0.0 when no gate has a positive net",
              "turns": len(rows), "xlmr_accuracy": round(acc, 4), "reliability": reliability(rows),
              "gate_table": table, "chosen_gate": gate,
              "fresh_turns_below_gate": fresh_below, "fresh_turns": len(fresh_rows)}
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print("saved", a.out)


if __name__ == "__main__":
    main()
