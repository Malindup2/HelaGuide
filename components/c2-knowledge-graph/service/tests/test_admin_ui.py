"""The review page. Its script is a Python string, so a stray line break silently kills the whole
page. This test parses the script with Node (when installed) so that can never ship again."""

import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from app.admin_ui import app


def _script() -> str:
    html = TestClient(app).get("/").text
    return html.split("<script>")[1].split("</script>")[0]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")
def test_the_page_script_has_no_syntax_error(tmp_path):
    f = tmp_path / "page.js"
    f.write_text(_script(), encoding="utf-8")
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_the_page_names_the_actions_a_person_needs():
    html = TestClient(app).get("/").text
    for label in ("Read with model", "Read by sections", "Different service? File it",
                  "Approve ticked", "Reject unticked", "Write to graph"):
        assert label in html, label


def test_a_multi_part_page_read_as_one_service_says_so_without_overclaiming():
    html = TestClient(app).get("/").text
    assert "read as one service" in html
    assert "first service only" not in html      # many headings can be variants of ONE service


def test_the_page_says_how_many_facts_of_a_page_are_in_the_graph():
    html = TestClient(app).get("/").text
    assert "in graph" in html and "approved, not written" in html
    rows = TestClient(app).get("/api/files").json()
    assert rows and all({"in_graph", "approved_not_written", "rejected", "pending"} <= set(r) for r in rows)


def test_rows_start_ticked_so_review_is_by_exception():
    html = TestClient(app).get("/").text
    assert 'data-id="${f.id}" checked' in html          # approve by default
    assert "const unticked=" in html and "Reject unticked" in html
    assert "changed</span>" in html                     # a replacement is marked, not hidden


BS = chr(92)


def test_a_saved_page_is_identified_the_same_way_however_its_path_was_written():
    from app.admin_ui import _file_key

    assert _file_key("components/c2/research/data/crawl/archive/2026-10-11/ab12.md") == "archive/2026-10-11/ab12.md"
    windows = "C:" + BS + "x" + BS + "crawl" + BS + "archive" + BS + "2026-10-11" + BS + "ab12.md"
    assert _file_key(windows) == "archive/2026-10-11/ab12.md"


def test_the_all_pages_view_is_served_and_the_main_view_only_lists_what_is_left():
    c = TestClient(app)
    assert c.get("/all").status_code == 200
    html = c.get("/").text
    assert "rows.filter(f=>f.state===\"to_read\"||f.state===\"changed\")" in html
    assert "already read and the page has not changed" in open(
        __import__("app.admin_ui", fromlist=["x"]).__file__, encoding="utf-8").read()
