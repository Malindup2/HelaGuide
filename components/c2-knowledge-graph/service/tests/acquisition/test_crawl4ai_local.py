"""End to end through real Crawl4AI against a local HTTP server (no internet needed).

Skipped automatically when crawl4ai is not installed: pip install -e ".[crawl]"
"""

import asyncio
import functools
import http.server
import threading

import pytest

pytest.importorskip("crawl4ai")

from app.core.acquisition.fetch import Crawl4AIFetcher, PoliteFetcher  # noqa: E402
from app.core.acquisition.monitor import JsonlRunLog, run_pass  # noqa: E402
from app.core.acquisition.ratelimit import HostRateLimiter  # noqa: E402
from app.core.acquisition.robots import RobotsPolicy  # noqa: E402
from app.core.acquisition.seeds import Seed  # noqa: E402
from app.core.acquisition.store import SnapshotStore  # noqa: E402

BODY = "Applicants must bring the documents listed below to the counter. " * 6


def page(fee, visitors):
    return (f"<html><body><h1>Ordinary passport</h1><p>Fee for the normal service: {fee}.</p>"
            f"<p>{BODY}</p><ul><li>Birth certificate</li><li>National Identity Card</li></ul>"
            f"<p>Last updated: 01 September 2026</p><p>Visitors: {visitors}</p></body></html>")


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    web = tmp_path / "web"
    web.mkdir()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(web))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def publish(html):
        (web / "passport.html").write_text(html, encoding="utf-8")

    yield f"http://127.0.0.1:{server.server_port}", publish
    server.shutdown()


def test_real_crawl4ai_classifies_new_unchanged_and_content_changed(site, tmp_path):
    base, publish = site
    seed = Seed(f"{base}/passport.html", "svc:passport", "Immigration")

    async def one_pass():
        inner = Crawl4AIFetcher(http_only=True)
        fetcher = PoliteFetcher(inner, RobotsPolicy("TestBot/1.0"), HostRateLimiter(0.0))
        try:
            return await run_pass([seed], fetcher, SnapshotStore(tmp_path / "d"),
                                  JsonlRunLog(tmp_path / "d"))
        finally:
            await inner.aclose()

    publish(page("LKR. 10,000.00", "84,412"))
    assert asyncio.run(one_pass()).counts == {"NEW": 1}

    publish(page("LKR. 10,000.00", "84,977"))  # only the hit counter moved
    second = asyncio.run(one_pass())
    assert second.counts == {"UNCHANGED": 1} and second.to_extract == []

    publish(page("LKR. 11,000.00", "85,100"))  # the fee was corrected in place
    third = asyncio.run(one_pass())
    assert third.counts == {"CONTENT_CHANGED": 1}
    assert third.pages[0].detail["char_delta"] == 0
