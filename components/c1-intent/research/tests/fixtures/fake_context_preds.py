"""
FAKE per-turn predictions in the format of c1_context_experiment.ipynb, for dry runs and tests of context_eval.py.

The test sessions are the real ones (same split, same stitching as the notebook); the predicted intents, tokens and
latencies are made up. Every row has "fake": true, and context_eval.py prints a warning in summary.md.

    python tests/fixtures/fake_context_preds.py --out <dir> [--max-sessions 4] [--seeds 1,2,3]     # from research/
"""
import argparse
import json
import os
import random
import sys
import zlib

RESEARCH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RESEARCH, "experiments"))
import context_strategies as cs  # noqa: E402

# error rate per strategy on (first turn of a dialogue, follow-up turn); TF-IDF is a little worse
ERRORS = {"current_only": (0.10, 0.45), "window_2": (0.10, 0.12), "window_3": (0.10, 0.11),
          "keyword_summary": (0.12, 0.30), "structured_state": (0.10, 0.14), "summary": (0.10, 0.13),
          "full_history": (0.09, 0.10)}


def _read(path):
    with open(os.path.join(RESEARCH, path), encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()] if path.endswith(".jsonl") else json.load(fh)


def test_sessions(max_sessions=None):
    split = _read(cs.SPLIT_PATH)
    silver = _read("data/synthetic/silver_tokens.jsonl")
    sets = {"gold": cs.stitched_sessions(_read("data/gold_tokens.jsonl"), 0),
            "synthetic": cs.stitched_sessions([r for r in silver if r["dialogue_id"] in set(split["test"])], 0),
            "fresh": cs.stitched_sessions(_read("data/fresh_tokens.jsonl"), 0)}
    return {k: v[:max_sessions] if max_sessions else v for k, v in sets.items()}


def bot_text():
    bot = {}
    for path in ("data/seed_all.json", "data/synthetic/synthetic_dialogues.json", "data/fresh_dialogues_states.json"):
        for d in _read(path):
            b = None
            for i, t in enumerate(d["turns"]):
                if t.get("speaker") == "bot":
                    b = t["text"]
                else:
                    bot[(d["dialogue_id"], i)] = b
    return bot


def fake_runs(seeds=(1, 2, 3), max_sessions=None, strategies=cs.STRATEGIES, models=("xlmr", "tfidf"), noise_seed=0,
              with_inputs=True, sets=None, bot=None):
    """{(model, strategy, seed): rows}. The error rate depends only on the strategy, the model and whether the turn
    is a follow-up in its dialogue, never on code-mixing: within a turn position there is no H3 effect (a null for
    calibration). noise_seed draws a different, equally null, data set. with_inputs=False skips the model inputs
    and token counts (faster; for h3_calibration.py)."""
    sets = sets or test_sessions(max_sessions)
    bot = bot or bot_text()
    intents = sorted({r["intent"] for v in sets.values() for s in v for r in s})
    runs = {}
    for model in models:
        for st in strategies:
            for seed in seeds:
                rows = []
                for ts, sessions in sets.items():
                    for si, s in enumerate(sessions):
                        prev_pred = None
                        for pos, cur in enumerate(s):
                            key = f"{model}/{st}/{seed}/{ts}/{si}/{pos}" + (f"/n{noise_seed}" if noise_seed else "")
                            rng = random.Random(zlib.crc32(key.encode()))
                            follow = pos > 0 and s[pos - 1]["dialogue_id"] == cur["dialogue_id"]
                            err = ERRORS[st][follow] + (0.05 if model == "tfidf" else 0.0)
                            pred = cur["intent"] if rng.random() > err else rng.choice(
                                [i for i in intents if i != cur["intent"]])
                            x = cs.build_input(st, s[:pos], cur, prev_pred) if with_inputs else cur["text"]
                            prev_pred = pred
                            n, n_cur = round(1.4 * len(x.split())) + 2, round(1.4 * len(cur["text"].split())) + 2
                            rows.append({
                                "model": model, "strategy": st, "seed": seed, "test_set": ts,
                                "session_id": f"{ts}-{si:03d}", "session_pos": pos, "dialogue_id": cur["dialogue_id"],
                                "turn_index": cur["turn"], "code_mix": cur.get("code_mix"), "text": cur["text"],
                                "bot_text": bot[(cur["dialogue_id"], cur["turn"])], "input": x,
                                "gold_intent": cur["intent"], "pred_intent": pred,
                                "confidence": round(rng.uniform(0.4, 0.99), 4),
                                "tokens_xlmr": n, "tokens_cl100k": round(n * 1.8),
                                "context_tokens_xlmr": n - n_cur, "context_tokens_cl100k": round((n - n_cur) * 1.8),
                                "truncated": n > 128, "latency_ms": round((8 if model == "xlmr" else 1.5) + 0.02 * n, 3),
                                "build_ms": 0.1, "device": "cuda" if model == "xlmr" else "cpu", "fake": True})
                runs[(model, st, seed)] = rows
    return runs


def make_fake_preds(out_dir, seeds=(1, 2, 3), max_sessions=None, strategies=cs.STRATEGIES, models=("xlmr", "tfidf"),
                    noise_seed=0):
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for (model, st, seed), rows in fake_runs(seeds, max_sessions, strategies, models, noise_seed).items():
        path = os.path.join(out_dir, f"{model}__{st}__seed{seed}.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        paths.append(path)
    return paths


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-sessions", type=int, default=None, help="sessions per test set (default: all)")
    ap.add_argument("--seeds", default="1,2,3")
    ap.add_argument("--noise-seed", type=int, default=0, help="another null data set (0 = the default one)")
    a = ap.parse_args()
    ps = make_fake_preds(a.out, tuple(int(s) for s in a.seeds.split(",")), a.max_sessions, noise_seed=a.noise_seed)
    print(f"wrote {len(ps)} FAKE prediction files to {a.out}")
