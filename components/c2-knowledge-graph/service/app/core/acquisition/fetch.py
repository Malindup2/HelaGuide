"""Fetching pages. The rest of the component depends on the Fetcher protocol only."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from urllib.parse import urlparse

from app.core.acquisition.ratelimit import HostRateLimiter
from app.core.acquisition.robots import RobotsPolicy

USER_AGENT = "HelaGuideBot/0.1 (+https://github.com/Malindup2/HelaGuide; academic research)"

# Hosts whose TLS is misconfigured server-side (e.g. motortraffic.gov.lk answers with
# TLSV1_UNRECOGNIZED_NAME). Verification is relaxed for these ONLY, and every page fetched
# this way carries tls_relaxed=True so it keeps weaker provenance downstream. Never merge
# a relaxed-TLS fact into the trusted graph without that flag travelling with it.
RELAXED_TLS_HOSTS = frozenset({"www.motortraffic.gov.lk", "motortraffic.gov.lk"})


def needs_relaxed_tls(url: str) -> bool:
    return (urlparse(url).hostname or "").lower() in RELAXED_TLS_HOSTS


@dataclass
class FetchResult:
    url: str
    ok: bool
    status: int | None = None
    html: str = ""
    text: str = ""  # markdown text extracted from the page
    error: str = ""
    tls_relaxed: bool = False
    duration_ms: int = 0
    fetched_at: str = ""
    source_type: str = "html"  # "html" or "pdf"
    content: bytes = b""  # original file bytes, set for PDFs


class Fetcher(Protocol):
    async def fetch(self, url: str) -> FetchResult: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Crawl4AIFetcher:
    """Fetches with Crawl4AI. Install the extra first: pip install -e ".[crawl]".

    http_only=True is a plain GET (fast, enough for the server-rendered pages most
    .gov.lk sites serve). Browser mode renders JavaScript and is for pages whose text
    comes back near-empty in HTTP mode.
    """

    def __init__(self, http_only: bool = True, page_timeout_ms: int = 120_000) -> None:
        self.http_only = http_only
        self.page_timeout_ms = page_timeout_ms
        self._crawlers: dict[bool, object] = {}

    async def _crawler(self, verify_ssl: bool):
        if verify_ssl in self._crawlers:
            return self._crawlers[verify_ssl]
        from crawl4ai import AsyncWebCrawler, BrowserConfig

        if not self.http_only:
            crawler = AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False))
        else:
            import aiohttp
            from crawl4ai import HTTPCrawlerConfig
            from crawl4ai.async_crawler_strategy import AsyncHTTPCrawlerStrategy

            # aiohttp ignores proxy environment variables unless trust_env is set.
            if not getattr(aiohttp.ClientSession, "_trust_env_patched", False):
                original = aiohttp.ClientSession.__init__

                def patched(self, *a, **kw):
                    kw.setdefault("trust_env", True)
                    return original(self, *a, **kw)

                aiohttp.ClientSession.__init__ = patched
                aiohttp.ClientSession._trust_env_patched = True

            strategy = AsyncHTTPCrawlerStrategy(
                browser_config=HTTPCrawlerConfig(
                    method="GET", follow_redirects=True, verify_ssl=verify_ssl
                )
            )
            crawler = AsyncWebCrawler(crawler_strategy=strategy)
        await crawler.__aenter__()
        self._crawlers[verify_ssl] = crawler
        return crawler

    async def fetch(self, url: str) -> FetchResult:
        from crawl4ai import CrawlerRunConfig

        relaxed = needs_relaxed_tls(url)
        started = time.monotonic()
        try:
            crawler = await self._crawler(verify_ssl=not relaxed)
            result = await crawler.arun(
                url=url,
                config=CrawlerRunConfig(word_count_threshold=5, page_timeout=self.page_timeout_ms),
            )
            elapsed = int((time.monotonic() - started) * 1000)
            if not result.success:
                return FetchResult(url, False, error=result.error_message or "failed",
                                   tls_relaxed=relaxed, duration_ms=elapsed, fetched_at=_now())
            md = result.markdown
            text = md.raw_markdown if hasattr(md, "raw_markdown") else str(md)
            return FetchResult(url, True, status=result.status_code, html=result.html or "",
                               text=text, tls_relaxed=relaxed, duration_ms=elapsed,
                               fetched_at=_now())
        except Exception as e:  # keep the run going; the failure is logged per page
            elapsed = int((time.monotonic() - started) * 1000)
            return FetchResult(url, False, error=f"{type(e).__name__}: {e}",
                               tls_relaxed=relaxed, duration_ms=elapsed, fetched_at=_now())

    async def aclose(self) -> None:
        for crawler in self._crawlers.values():
            await crawler.__aexit__(None, None, None)
        self._crawlers.clear()


class PoliteFetcher:
    """Wraps any Fetcher with robots.txt compliance and per-host rate limiting."""

    def __init__(self, inner: Fetcher, robots: RobotsPolicy, limiter: HostRateLimiter) -> None:
        self.inner = inner
        self.robots = robots
        self.limiter = limiter

    async def fetch(self, url: str) -> FetchResult:
        if not await self.robots.allowed(url):
            return FetchResult(url, False, error="blocked by robots.txt",
                               tls_relaxed=needs_relaxed_tls(url), fetched_at=_now())
        await self.limiter.wait(url, await self.robots.crawl_delay(url))
        return await self.inner.fetch(url)
