"""robots.txt, rate limiting and the polite wrapper, with no network."""

import asyncio

from app.core.acquisition.fetch import FetchResult, PoliteFetcher, needs_relaxed_tls
from app.core.acquisition.ratelimit import HostRateLimiter
from app.core.acquisition.robots import RobotsPolicy

UA = "TestBot/1.0"


def run(coro):
    return asyncio.run(coro)


def robots_returning(status: int, body: str = ""):
    calls = []

    async def fetch(url: str):
        calls.append(url)
        return status, body

    fetch.calls = calls
    return fetch


# ------------------------------------------------------------------------- robots
def test_robots_disallow_is_obeyed():
    body = "User-agent: *\nDisallow: /private/\n"
    policy = RobotsPolicy(UA, robots_returning(200, body))
    assert run(policy.allowed("https://www.drc.gov.lk/services/")) is True
    assert run(policy.allowed("https://www.drc.gov.lk/private/x")) is False


def test_missing_robots_txt_allows_everything():
    policy = RobotsPolicy(UA, robots_returning(404))
    assert run(policy.allowed("https://www.drp.gov.lk/anything")) is True


def test_unreadable_robots_txt_is_treated_as_disallowed():
    for status in (500, 503, 0):
        policy = RobotsPolicy(UA, robots_returning(status))
        assert run(policy.allowed("https://www.rgd.gov.lk/")) is False


def test_robots_is_fetched_once_per_host():
    fetcher = robots_returning(200, "User-agent: *\nAllow: /\n")
    policy = RobotsPolicy(UA, fetcher)

    async def go():
        await policy.allowed("https://a.gov.lk/1")
        await policy.allowed("https://a.gov.lk/2")
        await policy.allowed("https://b.gov.lk/1")

    run(go())
    assert fetcher.calls == ["https://a.gov.lk/robots.txt", "https://b.gov.lk/robots.txt"]


def test_crawl_delay_is_read():
    policy = RobotsPolicy(UA, robots_returning(200, "User-agent: *\nCrawl-delay: 7\n"))
    assert run(policy.crawl_delay("https://x.gov.lk/")) == 7.0


# --------------------------------------------------------------------- rate limit
def test_same_host_requests_are_spaced():
    now = [0.0]
    slept = []

    async def sleep(seconds):
        slept.append(seconds)
        now[0] += seconds

    limiter = HostRateLimiter(2.0, clock=lambda: now[0], sleep=sleep)

    async def go():
        await limiter.wait("https://a.gov.lk/1")
        await limiter.wait("https://a.gov.lk/2")
        await limiter.wait("https://a.gov.lk/3")

    run(go())
    assert slept == [2.0, 2.0]


def test_different_hosts_do_not_wait_for_each_other():
    slept = []

    async def sleep(seconds):
        slept.append(seconds)

    limiter = HostRateLimiter(2.0, clock=lambda: 0.0, sleep=sleep)

    async def go():
        await limiter.wait("https://a.gov.lk/")
        await limiter.wait("https://b.gov.lk/")

    run(go())
    assert slept == []


def test_robots_crawl_delay_can_widen_the_gap():
    now = [0.0]
    slept = []

    async def sleep(seconds):
        slept.append(seconds)
        now[0] += seconds

    limiter = HostRateLimiter(2.0, clock=lambda: now[0], sleep=sleep)

    async def go():
        await limiter.wait("https://a.gov.lk/1", interval=10.0)
        await limiter.wait("https://a.gov.lk/2", interval=10.0)

    run(go())
    assert slept == [10.0]


# ----------------------------------------------------------------- polite fetcher
class FakeInner:
    def __init__(self):
        self.urls = []

    async def fetch(self, url):
        self.urls.append(url)
        return FetchResult(url, True, status=200, html="<p>x</p>", text="x")


def polite(robots_body, inner):
    async def sleep(_):
        pass

    return PoliteFetcher(
        inner,
        RobotsPolicy(UA, robots_returning(200, robots_body)),
        HostRateLimiter(0.0, clock=lambda: 0.0, sleep=sleep),
    )


def test_blocked_url_is_never_requested():
    inner = FakeInner()
    fetcher = polite("User-agent: *\nDisallow: /private/\n", inner)
    result = run(fetcher.fetch("https://a.gov.lk/private/page"))
    assert result.ok is False
    assert result.error == "blocked by robots.txt"
    assert inner.urls == []


def test_allowed_url_is_passed_through():
    inner = FakeInner()
    fetcher = polite("User-agent: *\nAllow: /\n", inner)
    result = run(fetcher.fetch("https://a.gov.lk/services"))
    assert result.ok and inner.urls == ["https://a.gov.lk/services"]


def test_relaxed_tls_applies_only_to_the_listed_host():
    assert needs_relaxed_tls("https://www.motortraffic.gov.lk/web/index.php")
    assert not needs_relaxed_tls("https://www.immigration.gov.lk/pages_e.php?id=8")
