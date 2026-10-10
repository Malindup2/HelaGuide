"""robots.txt policy. Government servers are not to be burdened or crawled against their wishes."""

from __future__ import annotations

import asyncio
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

# (status_code, body). status 0 means the request itself failed.
RobotsFetcher = Callable[[str], Awaitable[tuple[int, str]]]


async def fetch_robots_txt(url: str, user_agent: str, timeout: float = 15.0) -> tuple[int, str]:
    """Fetch a robots.txt with the stdlib, honouring proxy environment variables."""

    def _get() -> tuple[int, str]:
        req = urllib.request.Request(url, headers={"User-Agent": user_agent})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https only)
                return resp.status, resp.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            return e.code, ""
        except Exception:
            return 0, ""

    return await asyncio.to_thread(_get)


class RobotsPolicy:
    """Per-host robots.txt cache.

    * 2xx: parse and obey it.
    * 4xx (no robots.txt): everything is allowed, as the standard says.
    * 5xx or unreachable: treat the host as disallowed for this run. When we cannot read
      the rules we do not guess in our own favour.
    """

    def __init__(self, user_agent: str, fetcher: RobotsFetcher | None = None) -> None:
        self.user_agent = user_agent
        self._fetch = fetcher or (lambda u: fetch_robots_txt(u, user_agent))
        self._cache: dict[str, RobotFileParser | bool] = {}
        self._lock = asyncio.Lock()

    async def _rules(self, origin: str) -> RobotFileParser | bool:
        async with self._lock:
            if origin not in self._cache:
                status, body = await self._fetch(f"{origin}/robots.txt")
                if 200 <= status < 300:
                    parser = RobotFileParser()
                    parser.parse(body.splitlines())
                    self._cache[origin] = parser
                elif 400 <= status < 500:
                    self._cache[origin] = True
                else:
                    self._cache[origin] = False
            return self._cache[origin]

    async def allowed(self, url: str) -> bool:
        parts = urlparse(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        rules = await self._rules(origin)
        if isinstance(rules, bool):
            return rules
        return rules.can_fetch(self.user_agent, url)

    async def crawl_delay(self, url: str) -> float | None:
        parts = urlparse(url)
        rules = await self._rules(f"{parts.scheme}://{parts.netloc}")
        if isinstance(rules, bool):
            return None
        delay = rules.crawl_delay(self.user_agent)
        return float(delay) if delay is not None else None
