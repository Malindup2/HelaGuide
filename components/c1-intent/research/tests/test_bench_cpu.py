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


def test_scale_claim_section_marks_the_estimate():
    from context_eval import _bench_lines
    rows = [{"model": "c1_engine", "strategy": "window_3 (deployed, full pipeline)", "threads": 1,
             "latency_p50_ms": 300, "latency_p95_ms": 450, "throughput_turns_per_s": 3.1, "est_4core_turns_per_s": 12.4,
             "peak_memory_mb": 1800, "tokens_per_turn": 30, "tokens_per_conversation": 200,
             "scale_verdict": "supported: deployed engine p95 450 ms"}]
    text = "\n".join(_bench_lines(rows))
    assert "**supported: deployed engine p95 450 ms**" in text and "ESTIMATE" in text and "12.4" in text
