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


def _scale(verdict, p95):
    from context_eval import scale_lines
    rows = [{"model": "xlmr", "strategy": "window_3", "threads": 1, "latency_p50_ms": 90, "latency_p95_ms": 130,
             "throughput_turns_per_s": 10.0, "est_4core_turns_per_s": 40.0, "peak_memory_mb": 1200,
             "tokens_per_turn": 30, "tokens_per_conversation": 200},
            {"model": "c1_engine", "strategy": "window_3 (deployed, full pipeline)", "threads": 1,
             "latency_p50_ms": 300, "latency_p95_ms": p95, "throughput_turns_per_s": 3.1, "est_4core_turns_per_s": 12.4,
             "peak_memory_mb": 1800, "tokens_per_turn": 30, "tokens_per_conversation": 200, "scale_verdict": verdict}]
    res = {"settings": {"strategies": ["window_3"]},
           "metrics": {"xlmr/window_3/heldout": {"tokens_xlmr_mean": [30.0], "tokens_cl100k_mean": [70.0],
                                                 "latency_ms_mean": [9.0], "device": "cuda"}}}
    return "\n".join(scale_lines(rows, res, "heldout"))


def test_scale_claim_separates_strategy_cost_from_the_pipeline():
    text = _scale("supported: deployed engine p95 450 ms", 450)
    assert "**supported: deployed engine p95 450 ms**" in text and "ESTIMATE" in text and "12.4" in text
    assert text.index("### Context-strategy cost") < text.index("### Full-pipeline cost")
    assert "under about 1 s in total" in text and "Why two intent calls per turn" in text
    assert "Fixes (future work)" not in text                     # only listed when the budget is missed


def test_scale_claim_lists_reasons_and_fixes_when_over_budget():
    text = _scale("not supported: deployed engine p95 1455 ms", 1455)
    assert "three separate fp32 XLM-R models" in text and "shared XLM-R encoder with three heads" in text
    assert "int8" in text and "one intent call per turn" in text


def test_scale_claim_before_the_benchmark_runs():
    from context_eval import scale_lines
    res = {"settings": {"strategies": []}, "metrics": {}}
    text = "\n".join(scale_lines(None, res, "heldout"))
    assert "not run yet" in text and "### Full-pipeline cost" in text
