"""The HTML report: the terminal demo output turned into headings, tables, cards and a chart."""
import re

import pytest

from app.cli import report
from app.cli._common import banner, table

MINI = "\n".join([
    "Warning: You are sending unauthenticated requests to the HF Hub.",
    "",
    "=" * 78, "PART 1 · SET-UP: C3 owns the confidence of every fact", "=" * 78,
    "registered      : 58 facts across 8 services, 15 reporters",
    "embedding model : sentence-transformers/all-mpnet-base-v2   (inference only)",
    "",
    "A few facts and the confidence record C3 created for each:",
    table(["fact_id", "stored value", "confidence", "status"], [["passport:fee:normal", "11000 LKR", "90%", "active"]]),
    "",
    "=" * 78, "PART 2 · FACT GROUNDING: which stored fact is the citizen disputing?", "=" * 78,
    "",
    "--- ft-X1  (freetext, english) ---",
    "message : Paid <b>12,000</b> & more -> not 11,000.",
    table(["candidate fact", "score", "similarity"], [["passport:fee:normal", "0.748", "0.697"], ["passport:fee:one_day", "0.587", "0.675"]]),
    "decision: GROUNDED -> passport:fee:normal   | expected: grounded passport:fee:normal   OK",
    "",
    "=" * 78, "PART 3 · CONFIDENCE STORY: passport fee", "=" * 78,
    "Stored fact: passport:fee:normal = 11000 LKR.  Starting confidence 90%.",
    "",
    "[1] ft-A1   path=freetext   reporter=anon-0001",
    "    message   : first report   (English)",
    "    evidence  : E=0.865   ->   confidence 90.0% -> 76.0%   [disputed]",
    "    citizen sees: 76%  |  no warning yet   (confidence-lowering updates so far: 1)",
    "",
    table(["report", "kind", "T", "confidence", "warning"], [["ft-A1", "dispute", "0.865", "76%", "NONE"], ["ft-A6", "dispute", "0.954", "50%", "VERIFY_BEFORE_VISIT"]]),
    "chart saved: C:\\nowhere\\passport_fee_story.svg",
    "",
    "Audit trail (every change is recorded with its reason):",
    "   None -> 0.9   initial confidence (Algorithm 0a)",
    "   0.9 -> 0.76   1 dispute / 0 support reports",
    "",
    '{"fact_id": "svc:passport:fee:normal", "confidence": 0.9, "status": "ok"}   [valid against contracts/schema/v1/trust.schema.json]',
    "{", '  "confidence_pct": 90,', '  "warning_code": "NONE"', "}",
    "",
    "=" * 78, "PART 7 · DO THE FORMULAS BEHAVE AS CLAIMED? (live property checks)", "=" * 78,
    table(["property", "result", "detail"], [["calibration", "PASS", "0.5000 (target 0.5)"]]),
    "",
    "8/8 checks passed",
    "OVERALL: 41/43 correct (95%)",
])


def test_parse_finds_sections_tables_cards_json_and_the_audit_trail():
    secs = report.parse(MINI)
    assert [s["part"] for s in secs][-4:] == [1, 2, 3, 7]
    blocks = {s["part"]: s["blocks"] for s in secs}
    t1 = [b for b in blocks[1] if b["type"] == "table"][0]
    assert t1["headers"] == ["fact_id", "stored value", "confidence", "status"] and t1["rows"][0][2] == "90%"
    cand = [b for b in blocks[2] if b["type"] == "table"][0]
    assert len(cand["rows"]) == 2 and cand["rows"][1][0] == "passport:fee:one_day"      # the decision line is NOT a table row
    assert any(b["type"] == "kv" and b["key"] == "decision" for b in blocks[2])
    assert any(b["type"] == "card" and b["title"] == "ft-X1" for b in blocks[2])
    assert any(b["type"] == "card" and b["kind"] == "step" for b in blocks[3])
    assert [b for b in blocks[3] if b["type"] == "table" and b.get("audit")][0]["rows"][1][:2] == ["0.9", "0.76"]
    js = [b for b in blocks[3] if b["type"] == "json"]
    assert len(js) == 2 and js[0]["data"]["confidence"] == 0.9 and "valid against" in js[0]["note"] and js[1]["data"]["warning_code"] == "NONE"
    assert not any("HF Hub" in str(b) for s in secs for b in s["blocks"])                # the stray warning is dropped


def test_render_gives_headings_explanations_tables_and_colour_coded_chips():
    h = report.render(report.parse(MINI), MINI, "a test")
    assert h.count("<section") == 4 and "PART 3" in h and "Different citizens report the same passport fee" in h
    assert h.count("<table") == 5
    assert 'class="chip bad">50%' in h and 'class="chip ok">76%' in h                       # colour follows the warning, not the number
    assert 'class="chip bad">VERIFY_BEFORE_VISIT' in h and 'class="chip ok">PASS' in h
    assert 'class="best"' in h                                                              # the top candidate fact is highlighted
    assert "90.0% → 76.0%" in h                                                              # arrows are drawn as arrows
    assert re.search(r"41/43", h) and "8/8" in h                                            # the summary figures
    assert "https://" not in h.replace("https://www.w3.org", "") and "<script" not in h     # one offline page, no scripts


def test_text_from_the_demo_can_never_inject_html():
    h = report.render(report.parse(MINI), MINI, "<script>alert(1)</script>")
    assert "<b>12,000</b>" not in h and "&lt;b&gt;12,000&lt;/b&gt;" in h
    assert "<script>alert(1)</script>" not in h


def test_a_saved_output_is_read_even_when_powershell_saved_it_as_utf16(tmp_path):
    f = tmp_path / "demo_output.txt"
    f.write_bytes(MINI.encode("utf-16"))
    assert report.read_text(f).startswith("Warning:")
    out = tmp_path / "r.html"
    report.main(["--from-file", str(f), "--out", str(out), "--no-open"])
    assert out.read_text(encoding="utf-8").count("<section") == 4
    g = tmp_path / "plain.txt"
    g.write_text(MINI + "\nසිංහල", encoding="utf-8")
    assert "සිංහල" in report.read_text(g)


def test_input_that_is_not_a_demo_output_is_refused(tmp_path, capsys):
    f = tmp_path / "x.txt"
    f.write_text("hello\nworld\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        report.main(["--from-file", str(f), "--out", str(tmp_path / "r.html"), "--no-open"])
    assert "No demo output found" in capsys.readouterr().out


def test_the_full_report_from_a_real_demo_run(tmp_path):
    out = tmp_path / "report.html"
    report.main(["--sqlite", "--embedding", "hash", "--out", str(out), "--no-open"])
    h = out.read_text(encoding="utf-8")
    for n in range(1, 8):
        assert f"PART {n}" in h, n
    assert h.count("<table") >= 14 and h.count('class="card"') >= 16 and h.count('class="json"') == 4
    assert "8/8" in h and "VERIFY_BEFORE_VISIT" in h and "schema valid" in h
    assert 'class="chip bad">50%' in h                                                     # the passport fee ends flagged
