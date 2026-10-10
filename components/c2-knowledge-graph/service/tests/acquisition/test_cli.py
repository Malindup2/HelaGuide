import json

from app.core.acquisition.cli import main


def test_check_seeds_prints_a_summary(tmp_path, capsys):
    seeds = tmp_path / "s.yaml"
    seeds.write_text("seeds:\n  - {url: https://a.gov.lk/1, service: svc:passport, agency: DIE, verified: true}\n"
                     "  - {url: https://a.gov.lk/2, service: svc:passport, agency: DIE}\n")
    assert main(["--check-seeds", "--seeds", str(seeds)]) == 0
    out = capsys.readouterr().out
    assert "2 pages, 1 verified" in out and "svc:passport" in out


def test_report_before_any_run_says_so(tmp_path, capsys):
    assert main(["--report", "--root", str(tmp_path)]) == 0
    assert "No repeat observations" in capsys.readouterr().out


def test_report_reads_the_change_log(tmp_path, capsys):
    rows = [{"ts": "t1", "run_id": "r1", "url": "u", "change": "NEW"},
            {"ts": "t2", "run_id": "r2", "url": "u", "change": "UNCHANGED"},
            {"ts": "t3", "run_id": "r3", "url": "u", "change": "CONTENT_CHANGED"}]
    (tmp_path / "changes.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    main(["--report", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert "real change rate" in out and "50.0%" in out
