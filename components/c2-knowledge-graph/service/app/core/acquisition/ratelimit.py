"""Per-host rate limiting so a crawl never hammers one government server."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from urllib.parse import urlparse


class HostRateLimiter:
    """Guarantees at least `min_interval` seconds between requests to the same host."""

    def __init__(
        self,
        min_interval: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._next_allowed: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def wait(self, url: str, interval: float | None = None) -> None:
        """Block until `url`'s host may be contacted again, then reserve the slot."""
        host = (urlparse(url).hostname or "").lower()
        gap = max(self.min_interval, interval or 0.0)
        async with self._lock:
            now = self._clock()
            ready = self._next_allowed.get(host, now)
            delay = max(0.0, ready - now)
            self._next_allowed[host] = max(now, ready) + gap
        if delay:
            await self._sleep(delay)
