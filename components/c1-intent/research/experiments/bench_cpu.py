"""
CPU deployment benchmark (scale claim): what each context strategy costs per turn on CPU, and whether the deployed
C1 engine is fast and small enough to serve citizens.

Run from research/ (CPU only; about 10-20 minutes; close other heavy programs first):
    python experiments/bench_cpu.py --out-dir results/context_v2
    python experiments/bench_cpu.py --max-turns 40 --repeats 1 ...      # quick check

What it measures, on the held-out test sessions (synthetic test part + fresh, stitched with seed 0, as in the notebook):
  1. Intent model per strategy, batch size 1 (one citizen message at a time):
       XLM-R  run_v2_seed1's intent model reading each strategy's input. It was trained on window_3 inputs, so this
              measures cost (latency grows with the input), not accuracy; accuracy is in context_eval.py.
       TF-IDF + LogReg trained here on the same strategy's training sessions (train part of the split, seed 1).
     Per turn: build the input + tokenize + predict. structured_state reads the model's own previous prediction.
  2. The deployed engine end to end (C1Engine + Session, window_3, rules + XLM-R NER fallback): language ID, two
     intent calls, NER, the tracker and the intent policy, per turn.
  Reported: latency p50 / p95 (ms), throughput (turns per second, one stream, batch 1), peak process memory (MB),
  tokens per turn and per conversation (XLM-R tokenizer, with <s> and </s>).
  4-core server: an ESTIMATE, not a measurement: 4 worker processes with 1 thread each, throughput = 4 x the
  single-thread throughput (assumes no contention), memory = 4 x one worker's peak.
Scale verdict for the deployed engine (thresholds set here, changeable with flags): supported when its p95 latency at
1 thread is <= --latency-budget-ms (default 500 ms per turn) and one worker's peak memory is <= --memory-budget-mb
(default 2048 MB).

Writes deployment_benchmark.csv and deployment_benchmark.json (machine details); context_eval.py puts the scale claim
into summary.md from the CSV.
"""
import argparse
import json
import os
import platform
import multiprocessing as mp
import random
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import context_strategies as cs  # noqa: E402
from context_eval import write_csv  # noqa: E402
from dst_eval import load_json, load_jsonl  # noqa: E402

MAX_LEN = 128
WORKERS_4CORE = 4


def held_out_sessions(max_turns=None):
    split = load_json(cs.SPLIT_PATH)
    silver = load_jsonl("data/synthetic/silver_tokens.jsonl")
    test = set(split["test"])
    sessions = cs.stitched_sessions([r for r in silver if r["dialogue_id"] in test], 0) + \
        cs.stitched_sessions(load_jsonl("data/fresh_tokens.jsonl"), 0)
    if max_turns:
        out, n = [], 0
        for s in sessions:
            if n >= max_turns:
                break
            out.append(s)
            n += len(s)
        sessions = out
    train = cs.stitched_sessions([r for r in silver if r["dialogue_id"] not in test], 1)
    return sessions, train


def peak_mb():
    import psutil
    mi = psutil.Process().memory_info()
    return round(getattr(mi, "peak_wset", getattr(mi, "rss", 0)) / 2 ** 20, 1)      # peak working set on Windows


def summarise(times_ms, n_turns, wall_s):
    return {"latency_p50_ms": round(float(np.percentile(times_ms, 50)), 1),
            "latency_p95_ms": round(float(np.percentile(times_ms, 95)), 1),
            "latency_mean_ms": round(float(np.mean(times_ms)), 1),
            "throughput_turns_per_s": round(n_turns / wall_s, 2)}


def bench_strategy(predict, strategy, sessions, count_plain, count_full, repeats):
    """predict(text) -> intent. Times build + predict for every turn, session by session."""
    times, tok_turn, tok_conv = [], [], []
    predict(sessions[0][0]["text"])                       # warm-up
    wall = 0.0
    for rep in range(repeats):
        t_pass = time.perf_counter()
        for s in sessions:
            prev, conv = None, 0
            for pos, cur in enumerate(s):
                t0 = time.perf_counter()
                x = cs.build_input(strategy, s[:pos], cur, prev, count_tokens=count_plain)
                prev = predict(x)
                times.append((time.perf_counter() - t0) * 1000)
                if rep == 0:
                    n = count_full(x)
                    tok_turn.append(n)
                    conv += n
            if rep == 0:
                tok_conv.append(conv)
        wall += time.perf_counter() - t_pass
    out = summarise(times, len(times), wall)
    out.update(tokens_per_turn=round(float(np.mean(tok_turn)), 1),
               tokens_per_conversation=round(float(np.mean(tok_conv)), 1))
    return out


def engine_bench(model_dir, threads, repeats, max_turns):
    """The deployed engine end to end, in its own process, so its peak memory is one worker's."""
    import torch
    from c1_engine import C1Engine
    sessions, _ = held_out_sessions(max_turns)
    engine = C1Engine(model_dir, device="cpu", use_ner=True)
    engine.new_session().step("mata passport ekak ganna one")                       # warm-up
    after_load = peak_mb()
    out = []
    for th in threads:
        torch.set_num_threads(th)
        times, wall = [], 0.0
        for _ in range(repeats):
            t_pass = time.perf_counter()
            for s in sessions:
                sess, bot = engine.new_session(), None
                for cur in s:
                    t0 = time.perf_counter()
                    res = sess.step(cur["text"], bot)
                    times.append((time.perf_counter() - t0) * 1000)
                    bot = res.get("reply")
            wall += time.perf_counter() - t_pass
        out.append({"threads": th, **summarise(times, len(times), wall), "peak_memory_mb": peak_mb()})
    return after_load, out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out-dir", default="results/context_v2")
    ap.add_argument("--model-dir", default="models/c1/run_v2_seed1")
    ap.add_argument("--threads", default="1,4", help="torch threads to measure, e.g. 1,4 (1 is used for the estimate)")
    ap.add_argument("--repeats", type=int, default=2, help="passes over the test sessions per strategy")
    ap.add_argument("--max-turns", type=int, default=None, help="use only the first sessions, about this many turns")
    ap.add_argument("--no-tfidf", action="store_true")
    ap.add_argument("--latency-budget-ms", type=float, default=500.0)
    ap.add_argument("--memory-budget-mb", type=float, default=2048.0)
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args(argv)
    os.makedirs(a.out_dir, exist_ok=True)
    out_csv, out_json = (os.path.join(a.out_dir, f"deployment_benchmark.{x}") for x in ("csv", "json"))
    if (os.path.exists(out_csv) or os.path.exists(out_json)) and not a.overwrite:
        sys.exit(f"{a.out_dir} already has deployment_benchmark.*; pass --overwrite")

    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    threads = [int(t) for t in a.threads.split(",")]
    sessions, train = held_out_sessions(a.max_turns)
    n_turns = sum(len(s) for s in sessions)
    print(f"{len(sessions)} held-out sessions, {n_turns} turns; threads {threads}; repeats {a.repeats}")

    tok = AutoTokenizer.from_pretrained(os.path.join(a.model_dir, "intent"))
    tok.truncation_side = "left"
    model = AutoModelForSequenceClassification.from_pretrained(os.path.join(a.model_dir, "intent")).float().eval()
    id2label = model.config.id2label
    count_plain = lambda t: len(tok(t, add_special_tokens=False)["input_ids"])
    count_full = lambda t: len(tok(t, truncation=False)["input_ids"])
    mem_after_load = peak_mb()

    def xlmr_predict(text):
        with torch.no_grad():
            enc = tok(text, truncation=True, max_length=MAX_LEN, return_tensors="pt")
            return id2label[int(model(**enc).logits[0].argmax())]

    rows = []
    for th in threads:
        torch.set_num_threads(th)
        for st in cs.STRATEGIES:
            r = bench_strategy(xlmr_predict, st, sessions, count_plain, count_full, a.repeats)
            rows.append({"model": "xlmr", "strategy": st, "threads": th, **r, "peak_memory_mb": peak_mb()})
            print(f"  xlmr  {st:17s} threads {th}: p50 {r['latency_p50_ms']} ms, p95 {r['latency_p95_ms']} ms, "
                  f"{r['throughput_turns_per_s']} turns/s, {r['tokens_per_turn']} tokens/turn")

    if not a.no_tfidf:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline, make_union
        for st in cs.STRATEGIES:
            xs, ys = [], []
            for s in train:
                for pos, cur in enumerate(s):
                    xs.append(cs.build_input(st, s[:pos], cur, s[pos - 1]["intent"] if pos else None, count_tokens=count_plain))
                    ys.append(cur["intent"])
            m = make_pipeline(make_union(TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True),
                                         TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True)),
                              LogisticRegression(max_iter=3000, C=10)).fit(xs, ys)
            r = bench_strategy(lambda x: m.predict([x])[0], st, sessions, count_plain, count_full, a.repeats)
            rows.append({"model": "tfidf", "strategy": st, "threads": 1, **r, "peak_memory_mb": peak_mb()})
            print(f"  tfidf {st:17s}: p50 {r['latency_p50_ms']} ms, p95 {r['latency_p95_ms']} ms, "
                  f"{r['throughput_turns_per_s']} turns/s")

    # the deployed engine, end to end, in a fresh process (its peak memory is one worker's)
    with mp.get_context("spawn").Pool(1) as pool:
        engine_load_mb, eng_rows = pool.apply(engine_bench, (a.model_dir, threads, a.repeats, a.max_turns))
    for r in eng_rows:
        xl = next(x for x in rows if x["model"] == "xlmr" and x["strategy"] == "window_3" and x["threads"] == r["threads"])
        rows.append({"model": "c1_engine", "strategy": "window_3 (deployed, full pipeline)", **r,
                     "tokens_per_turn": xl["tokens_per_turn"], "tokens_per_conversation": xl["tokens_per_conversation"]})
        print(f"  engine window_3 full pipeline threads {r['threads']}: p50 {r['latency_p50_ms']} ms, "
              f"p95 {r['latency_p95_ms']} ms, {r['throughput_turns_per_s']} turns/s, peak {r['peak_memory_mb']} MB")

    # 4-core estimate from the 1-thread rows, and the verdict for the deployed engine
    for r in rows:
        if r["threads"] == 1:
            r["est_4core_turns_per_s"] = round(WORKERS_4CORE * r["throughput_turns_per_s"], 1)
            r["est_4core_memory_mb"] = round(WORKERS_4CORE * r["peak_memory_mb"], 0)
        r["estimate_note"] = "ESTIMATE: 4 workers x 1 thread, linear scaling assumed" if r["threads"] == 1 else ""
    eng = next((r for r in rows if r["model"] == "c1_engine" and r["threads"] == 1), None)
    if eng:
        ok_lat = eng["latency_p95_ms"] <= a.latency_budget_ms
        ok_mem = eng["peak_memory_mb"] <= a.memory_budget_mb
        eng["scale_verdict"] = (
            ("supported" if ok_lat and ok_mem else "not supported") +
            f": deployed engine p95 {eng['latency_p95_ms']} ms per turn at 1 thread (budget {a.latency_budget_ms:g} ms), "
            f"peak memory {eng['peak_memory_mb']} MB per worker (budget {a.memory_budget_mb:g} MB); "
            f"4-core ESTIMATE {eng['est_4core_turns_per_s']} turns/s")
    fields = list(dict.fromkeys(k for r in rows for k in r))
    write_csv(out_csv, [{k: r.get(k, "") for k in fields} for r in rows])
    import sklearn
    import transformers
    meta = {"run_at": time.strftime("%Y-%m-%d %H:%M"), "machine": platform.processor(), "platform": platform.platform(),
            "logical_cpus": os.cpu_count(), "python": platform.python_version(), "torch": torch.__version__,
            "transformers": transformers.__version__, "sklearn": sklearn.__version__, "model_dir": a.model_dir,
            "sessions": len(sessions), "turns": n_turns, "repeats": a.repeats, "threads": threads,
            "memory_after_xlmr_load_mb": mem_after_load, "engine_memory_after_load_mb": engine_load_mb,
            "budgets": {"latency_p95_ms": a.latency_budget_ms, "peak_memory_mb": a.memory_budget_mb},
            "note": "peak_memory_mb is the process peak so far (Windows peak working set). The per-strategy rows share "
                    "one process (XLM-R intent model, then TF-IDF), so later rows include earlier models; the deployed "
                    "engine runs in its own process, so its row is one worker's memory."}
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump({**meta, "rows": rows}, fh, indent=2)
    print(f"\n{eng['scale_verdict'] if eng else 'no engine row'}\nwrote {out_csv} and {out_json}")


if __name__ == "__main__":
    random.seed(0)
    main()
