"""make_figures.py runs on the committed results and skips, with a reason, a figure whose source is missing.
Run from research/:  python -m pytest -q tests
"""
import os

import pytest

RESEARCH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPECTED = {"lid_comparison.png", "dst_ablation.png", "token_tax.png", "latency_vs_tokens.png",
            "memory_vs_budget.png", "seed_spread.png", "h3_calibration.png"}


def _run(out_dir):
    import make_figures
    cwd = os.getcwd()
    os.chdir(RESEARCH)
    try:
        return make_figures.main(["--out-dir", str(out_dir)])
    finally:
        os.chdir(cwd)


def test_figures_build_from_the_committed_results(tmp_path):
    if not os.path.exists(os.path.join(RESEARCH, "results", "context_v2_final", "summary.md")):
        pytest.skip("committed results not found")
    made, skipped = _run(tmp_path)
    names = {os.path.basename(p) for p in made}
    assert names | {f"{n}.png" for n, _ in skipped} == EXPECTED            # every figure is either made or skipped
    assert {"lid_comparison.png", "dst_ablation.png", "token_tax.png", "h3_calibration.png"} <= names
    for p in made:
        assert os.path.getsize(p) > 20_000                                   # a real PNG, not an empty file
    assert all(why for _, why in skipped)                                    # a skip always says why


def test_missing_source_is_skipped_not_an_error(tmp_path, monkeypatch):
    import make_figures
    monkeypatch.setattr(make_figures, "FINAL", os.path.join("results", "no_such_folder"))
    made, skipped = _run(tmp_path)
    reasons = dict(skipped)
    for name in ("token_tax", "latency_vs_tokens", "memory_vs_budget", "seed_spread", "h3_calibration"):
        assert name in reasons and "missing" in reasons[name]
    assert {os.path.basename(p) for p in made} >= {"lid_comparison.png", "dst_ablation.png"}
