"""The ablation command: each component, switched off on its own, changes the result the way the design claims."""
import pytest

from app.cli import ablation
from app.cli.ablation import COPY, SPECIFIC, VAGUE, Cit, Rep, run


def test_every_claim_the_command_makes_holds():
    results = ablation.run_all()
    assert [r["key"] for r in results] == ["independence", "aggregation", "reputation", "age-recency"]
    assert all(r["check"] for r in results)


def test_without_independence_weighting_copies_flag_a_correct_fact():
    copies = [Rep(Cit(f"c{i}", age_days=30), COPY) for i in range(5)]
    full, off = run(copies), run(copies, rho=1.0)
    assert [round(x["I"], 2) for x in full] == [1.0, 0.6, 0.36, 0.22, 0.13]          # each further copy counts less
    assert all(x["I"] == 1.0 for x in off)
    assert full[-1]["status"] == "disputed" and off[-1]["status"] == "flagged"
    assert off[-1]["pct"] < 50 < full[-1]["pct"]
    assert full[0]["pct"] == pytest.approx(off[0]["pct"])                            # the first report is the same either way


def test_an_arithmetic_mean_trusts_weak_reports_more_and_strong_ones_the_same():
    vague = Rep(Cit("firstseen", age_days=0), VAGUE, visit_days_ago=None, claim=None)
    strong = Rep(Cit("veteran", a=6, age_days=200), SPECIFIC)
    g, a = run([vague])[0], run([vague], trust_mean="arithmetic")[0]
    assert a["T"] > 2 * g["T"]
    gs, as_ = run([strong])[0], run([strong], trust_mean="arithmetic")[0]
    assert abs(gs["T"] - as_["T"]) < 0.01


def test_with_reputation_off_a_bad_record_counts_like_a_good_one():
    good, bad = Rep(Cit("good", a=8)), Rep(Cit("bad", b=8))
    assert run([good])[0]["T"] > 2 * run([bad])[0]["T"]
    assert run([good], w_r=0.0)[0]["T"] == pytest.approx(run([bad], w_r=0.0)[0]["T"])


def test_with_age_or_recency_off_old_and_fresh_count_the_same():
    old, fresh = Rep(Cit("old", age_days=200)), Rep(Cit("fresh", age_days=1))
    assert run([fresh])[0]["T"] < 0.8 * run([old])[0]["T"]
    assert run([fresh], w_c=0.0)[0]["T"] == pytest.approx(run([old], w_c=0.0)[0]["T"])
    today, month = Rep(Cit("a"), visit_days_ago=0), Rep(Cit("b"), visit_days_ago=40)
    assert run([month])[0]["T"] < 0.8 * run([today])[0]["T"]
    assert run([month], w_t=0.0)[0]["T"] == pytest.approx(run([today], w_t=0.0)[0]["T"])


def test_the_command_prints_the_four_ablations_or_just_one(capsys):
    ablation.main([])
    out = capsys.readouterr().out
    for n in range(1, 5):
        assert f"ABLATION {n}" in out
    assert "WHAT IT PROVES" in out and "all hold" in out and "SUMMARY" in out
    ablation.main(["--only", "reputation"])
    one = capsys.readouterr().out
    assert "ABLATION 1 · REPUTATION OFF" in one and "ABLATION 2" not in one


def test_the_html_page_is_written_and_names_every_ablation(tmp_path, monkeypatch):
    monkeypatch.setenv("C3_OUT_DIR", str(tmp_path))
    ablation.main(["--html", "--no-open"])
    html = (tmp_path / "pp1_ablation.html").read_text(encoding="utf-8")
    assert html.count("<section>") == 5 and html.count("<table") == 7               # 4 ablations (6 tables) + the summary
    for title in ("Independence weighting off", "Arithmetic mean instead of geometric", "Reputation off", "Account age off"):
        assert title in html
    assert "What it proves" in html and "<script" not in html


def test_the_real_system_is_not_changed_by_the_ablation_switches():
    from app.core.config import C3Settings
    s = C3Settings()
    assert s.trust_mean == "geometric" and s.rho == 0.6 and (s.w_r, s.w_s, s.w_c, s.w_t) == (0.40, 0.25, 0.20, 0.15)
