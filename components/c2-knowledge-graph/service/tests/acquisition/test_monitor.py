"""A full monitoring pass against a fake fetcher: the 'second crawl costs nothing' evidence."""

import asyncio
import json

import pytest

from app.core.acquisition import report
from app.core.acquisition.fetch import FetchResult
from app.core.acquisition.fingerprint import ChangeKind
from app.core.acquisition.monitor import JsonlRunLog, run_pass
from app.core.acquisition.seeds import Seed, load_seeds, summarise
from app.core.acquisition.store import SnapshotStore

PASSPORT = Seed("https://gov.example/passport", "svc:passport", "Immigration")
NIC = Seed("https://gov.example/nic", "svc:nic", "Registration of Persons")

LONG = "Applicants must bring the documents listed below to the counter. " * 6


def html(fee="LKR 10,000", visitors="100", docs=2):
    items = "".join(f"<li>Document {i}</li>" for i in range(docs))
    return (f"<html><body><h1>Passport</h1><p>Fee: {fee}. {LONG}</p><ul>{items}</ul>"
            f"<p>Visitors: {visitors}</p></body></html>")


class Script:
    """Returns a scripted page per URL and counts how often each was fetched."""

    def __init__(self):
        self.pages = {}
        self.calls = []

    def set(self, url, page=None, error=None):
        self.pages[url] = (page, error)

    async def fetch(self, url):
        self.calls.append(url)
        page, error = self.pages[url]
        if error:
            return FetchResult(url, False, error=error, fetched_at="2026-10-06T09:00:00+00:00")
        import re
        text = re.sub(r"<[^>]+>", " ", page)
        return FetchResult(url, True, status=200, html=page, text=text,
                           fetched_at="2026-10-06T09:00:00+00:00")


def go(seeds, fetcher, store, log):
    return asyncio.run(run_pass(seeds, fetcher, store, log))


def test_three_passes_new_then_unchanged_then_content_changed(tmp_path):
    fetcher, store, log = Script(), SnapshotStore(tmp_path), JsonlRunLog(tmp_path)
    fetcher.set(PASSPORT.url, html())
    fetcher.set(NIC.url, html(fee="LKR 500"))

    first = go([PASSPORT, NIC], fetcher, store, log)
    assert first.counts == {"NEW": 2}
    assert len(first.to_extract) == 2

    # Only a visitor counter moved on one page: nothing may reach extraction.
    fetcher.set(PASSPORT.url, html(visitors="145"))
    second = go([PASSPORT, NIC], fetcher, store, log)
    assert second.counts == {"UNCHANGED": 2}
    assert second.to_extract == []

    # A fee is corrected in place on one page.
    fetcher.set(PASSPORT.url, html(fee="LKR 11,000", visitors="190"))
    third = go([PASSPORT, NIC], fetcher, store, log)
    assert third.counts == {"CONTENT_CHANGED": 1, "UNCHANGED": 1}
    assert [p.url for p in third.to_extract] == [PASSPORT.url]


def test_unreachable_page_is_logged_and_does_not_stop_the_run(tmp_path):
    fetcher, store, log = Script(), SnapshotStore(tmp_path), JsonlRunLog(tmp_path)
    fetcher.set(PASSPORT.url, error="SSLError: unrecognized name")
    fetcher.set(NIC.url, html())
    summary = go([PASSPORT, NIC], fetcher, store, log)
    assert summary.counts == {"UNREACHABLE": 1, "NEW": 1}
    assert store.latest(PASSPORT.url) is None  # nothing saved for a failed fetch


def test_unchanged_pages_are_not_archived_again(tmp_path):
    fetcher, store, log = Script(), SnapshotStore(tmp_path), JsonlRunLog(tmp_path)
    fetcher.set(PASSPORT.url, html())
    go([PASSPORT], fetcher, store, log)
    go([PASSPORT], fetcher, store, log)
    files = list((tmp_path / "archive").rglob("*.html"))
    assert len(files) == 1  # archived once, on first sight


def test_thin_pages_are_flagged(tmp_path):
    fetcher, store, log = Script(), SnapshotStore(tmp_path), JsonlRunLog(tmp_path)
    fetcher.set(PASSPORT.url, "<html><body><div id='app'></div></body></html>")
    summary = go([PASSPORT], fetcher, store, log)
    assert summary.pages[0].detail["thin_content"] is True


def test_logs_are_written_per_page_and_per_run(tmp_path):
    fetcher, store, log = Script(), SnapshotStore(tmp_path), JsonlRunLog(tmp_path)
    fetcher.set(PASSPORT.url, html())
    go([PASSPORT], fetcher, store, log)
    go([PASSPORT], fetcher, store, log)
    rows = [json.loads(line) for line in (tmp_path / "changes.jsonl").read_text().splitlines()]
    assert [r["change"] for r in rows] == ["NEW", "UNCHANGED"]
    assert rows[0]["service"] == "svc:passport" and rows[0]["run_id"] != rows[1]["run_id"]
    runs = [json.loads(line) for line in (tmp_path / "runs.jsonl").read_text().splitlines()]
    assert runs[1]["counts"] == {"UNCHANGED": 1} and runs[1]["to_extract"] == 0


def test_change_profile_excludes_first_sightings(tmp_path):
    fetcher, store, log = Script(), SnapshotStore(tmp_path), JsonlRunLog(tmp_path)
    fetcher.set(PASSPORT.url, html())
    go([PASSPORT], fetcher, store, log)
    go([PASSPORT], fetcher, store, log)
    fetcher.set(PASSPORT.url, html(fee="LKR 11,000"))
    go([PASSPORT], fetcher, store, log)
    p = report.profile(report.load_rows(tmp_path / "changes.jsonl"))
    assert p["observations"] == 2 and p["per_kind"] == {"UNCHANGED": 1, "CONTENT_CHANGED": 1}
    assert p["real_change_rate"] == 0.5 and p["structural_share_of_changes"] == 0.0


def test_seed_file_loads_and_rejects_duplicates(tmp_path):
    good = tmp_path / "seeds.yaml"
    good.write_text("seeds:\n  - {url: https://a.gov.lk/1, service: svc:passport, agency: DIE}\n"
                    "  - {url: https://a.gov.lk/2, service: svc:nic, agency: DRP, verified: true}\n")
    s = summarise(load_seeds(good))
    assert s["pages"] == 2 and s["verified"] == 1

    dup = tmp_path / "dup.yaml"
    dup.write_text("seeds:\n  - {url: https://a.gov.lk/1, service: svc:a, agency: x}\n"
                   "  - {url: https://a.gov.lk/1, service: svc:b, agency: y}\n")
    with pytest.raises(ValueError, match="duplicate"):
        load_seeds(dup)

    bad = tmp_path / "bad.yaml"
    bad.write_text("seeds:\n  - {url: https://a.gov.lk/1, service: Passport, agency: x}\n")
    with pytest.raises(ValueError, match="svc:"):
        load_seeds(bad)
