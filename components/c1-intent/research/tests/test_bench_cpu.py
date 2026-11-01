"""bench_cpu.py helpers (no model needed): the held-out sessions, the latency summary and the scale-claim section.
Run from research/:  python -m pytest -q tests
"""
import os

import pytest

RESEARCH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_held_out_sessions_are_the_notebook_test_turns():
    import bench_cpu
    cwd = os.getcwd()
    os.chdir(RESEARCH)
    try:
        sessions, train = bench_cpu.held_out_sessions()
        few, _ = bench_cpu.held_out_sessions(max_turns=20)
    finally:
        os.chdir(cwd)
    assert sum(len(s) for s in sessions) == 199 + 50            # synthetic test part + fresh
    test_ids = {r["dialogue_id"] for s in sessions for r in s}
    assert not test_ids & {r["dialogue_id"] for s in train for r in s}
    assert 20 <= sum(len(s) for s in few) < 20 + 16              # stops after the session that passes 20 turns


def test_summarise_latencies():
    import bench_cpu
    r = bench_cpu.summarise([10.0] * 95 + [100.0] * 5, n_turns=100, wall_s=2.0)
    assert r["latency_p50_ms"] == 10.0 and r["latency_p95_ms"] == pytest.approx(10.0, abs=5)
    assert r["throughput_turns_per_s"] == 50.0


def _row(model, strategy, threads, p50, p95, tokens, mem=1200, **kw):
    return {"model": model, "strategy": strategy, "threads": threads, "latency_p50_ms": p50, "latency_p95_ms": p95,
            "throughput_turns_per_s": 10.0, "est_4core_turns_per_s": 40.0 if threads == 1 else "",
            "peak_memory_mb": mem, "tokens_per_turn": tokens, "tokens_per_conversation": 7 * tokens, **kw}


def _scale(verdict, p95, mem=1800, one_thread=((12, 60), (30, 90), (52, 120))):
    """one_thread: (tokens, p50) of the 1-thread XLM-R rows; latency rising with tokens by default."""
    from context_eval import scale_lines
    rows = [_row("xlmr", st, 1, p50, p50 * 1.5, tok) for st, (tok, p50) in
            zip(("current_only", "window_3", "full_history"), one_thread)]
    rows += [_row("xlmr", st, 4, p50, p50 * 1.4, tok) for st, (tok, p50) in
             zip(("current_only", "window_3", "full_history"), ((12, 19), (30, 27), (52, 43)))]
    rows += [_row("c1_engine", "window_3 (deployed, full pipeline)", 1, 300, p95, 30, mem, scale_verdict=verdict),
             _row("c1_engine", "window_3 (deployed, full pipeline)", 4, 100, 152.8, 30, mem)]
    res = {"settings": {"strategies": ["window_3"]},
           "metrics": {"xlmr/window_3/heldout": {"tokens_xlmr_mean": [30.0], "tokens_cl100k_mean": [70.0],
                                                 "latency_ms_mean": [9.0], "device": "cuda"}}}
    meta = {"budgets": {"latency_p95_ms": 500.0, "peak_memory_mb": 2048.0}, "machine": "Intel64 Family 6 Model 154"}
    return "\n".join(scale_lines(rows, res, "heldout", meta))


def test_scale_claim_separates_strategy_cost_from_the_pipeline():
    text = _scale("supported: deployed engine p95 450 ms", 450)
    assert "**supported: deployed engine p95 450 ms**" in text and "ESTIMATE" in text
    assert text.index("### Context-strategy cost") < text.index("### Full-pipeline cost")
    assert "under about 1 s in total" in text and "Why two intent calls per turn" in text
    assert "Fixes (future work)" not in text                     # only listed when a budget is missed
    assert text.index("4 threads, batch size 1 (primary") < text.index("1 thread, batch size 1")
    assert "Caveat" not in text                                   # 1-thread latency rises with input here


def test_memory_miss_lists_only_the_memory_reason():
    text = _scale("not supported: deployed engine p95 412 ms; peak memory 3315.4 MB", 412.0, mem=3315.4)
    reasons = text[text.index("**Why it misses the budget:**"):text.index("**Fixes (future work):**")]
    assert "memory: peak 3315.4 MB" in reasons and "three separate fp32 XLM-R models" in reasons
    assert "four XLM-R forward passes" not in reasons and "Latency is within budget" in reasons
    fixes = text[text.index("**Fixes (future work):**"):]
    assert "four XLM-R forward passes" in fixes and "shared XLM-R encoder with three heads" in fixes and "int8" in fixes


def test_latency_miss_lists_the_forward_passes():
    text = _scale("not supported: deployed engine p95 1455 ms", 1455, mem=1800)
    reasons = text[text.index("**Why it misses the budget:**"):text.index("**Fixes (future work):**")]
    assert "latency: p95 1455" in reasons and "four XLM-R forward passes" in reasons
    assert "three separate fp32" not in reasons


def test_unreliable_one_thread_rows_get_the_caveat():
    # full_history (52 tokens) faster than current_only (12 tokens): latency does not rise with input length
    text = _scale("not supported: peak memory 3315.4 MB", 412.0, mem=3315.4,
                  one_thread=((12, 217.0), (30, 369.2), (52, 126.1)))
    assert "unreliable on this Intel hybrid CPU (Windows scheduling across P/E cores)" in text
    assert "latency does not rise with input length" in text
    assert "based on the 1-thread timings, so they are approximate" in text
    assert "the measured 4-thread p95 of the deployed engine is 152.8 ms. Memory alone decides the verdict" in text


def test_scale_claim_before_the_benchmark_runs():
    from context_eval import scale_lines
    res = {"settings": {"strategies": []}, "metrics": {}}
    text = "\n".join(scale_lines(None, res, "heldout"))
    assert "not run yet" in text and "### Full-pipeline cost" in text
