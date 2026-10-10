"""PDF pages: download the file, read its text layer, hand it to the same pipeline as HTML.

A PDF has no DOM, so html stays empty and the structure signature never changes; change
detection rests on the text digest alone. Scanned PDFs with no usable text layer come back
thin and are flagged by the monitor like any other thin page. No OCR here: see PLAN.md.
"""

from __future__ import annotations

import asyncio
import io
import ssl
import time
import urllib.request
from collections.abc import Awaitable, Callable
from urllib.parse import urlparse

from app.core.acquisition.fetch import USER_AGENT, Fetcher, FetchResult, _now, needs_relaxed_tls

PDF_MAX_BYTES = 25_000_000
PDF_TIMEOUT_S = 90

Downloader = Callable[[str], Awaitable[tuple[int, str, bytes]]]


def is_pdf_url(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")


def pdf_to_text(data: bytes) -> str:
    """Text layer of a PDF as Markdown, one section per page."""
    try:
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover
        raise RuntimeError('pypdf is missing: pip install -e ".[crawl]"') from e

    reader = PdfReader(io.BytesIO(data))
    parts = []
    for number, page in enumerate(reader.pages, start=1):
        body = (page.extract_text() or "").strip()
        parts.append(f"## Page {number}\n\n{body}")
    return "\n\n".join(parts)


def _download(url: str, relaxed_tls: bool) -> tuple[int, str, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    ctx = ssl._create_unverified_context() if relaxed_tls else None  # noqa: S323 (flagged hosts only)
    with urllib.request.urlopen(req, timeout=PDF_TIMEOUT_S, context=ctx) as resp:  # noqa: S310
        data = resp.read(PDF_MAX_BYTES + 1)
        return resp.status, resp.headers.get("Content-Type", ""), data


async def default_downloader(url: str) -> tuple[int, str, bytes]:
    return await asyncio.to_thread(_download, url, needs_relaxed_tls(url))


class PdfFetcher:
    def __init__(self, downloader: Downloader | None = None) -> None:
        self._download = downloader or default_downloader

    async def fetch(self, url: str) -> FetchResult:
        relaxed = needs_relaxed_tls(url)
        started = time.monotonic()

        def failed(error: str) -> FetchResult:
            return FetchResult(url, False, error=error, tls_relaxed=relaxed,
                               duration_ms=int((time.monotonic() - started) * 1000),
                               fetched_at=_now(), source_type="pdf")

        try:
            status, content_type, data = await self._download(url)
        except Exception as e:  # keep the run going; the failure is logged per page
            return failed(f"{type(e).__name__}: {e}")
        if len(data) > PDF_MAX_BYTES:
            return failed(f"pdf larger than {PDF_MAX_BYTES} bytes")
        if not data.startswith(b"%PDF"):
            return failed(f"not a pdf (content-type {content_type or 'unknown'})")
        try:
            text = pdf_to_text(data)
        except Exception as e:
            return failed(f"pdf unreadable: {type(e).__name__}: {e}")
        return FetchResult(url, True, status=status, text=text, content=data,
                           tls_relaxed=relaxed,
                           duration_ms=int((time.monotonic() - started) * 1000),
                           fetched_at=_now(), source_type="pdf")


class PdfAwareFetcher:
    """Sends .pdf URLs to the PDF fetcher and everything else to the page fetcher."""

    def __init__(self, pages: Fetcher, pdfs: Fetcher | None = None) -> None:
        self.pages = pages
        self.pdfs = pdfs or PdfFetcher()

    async def fetch(self, url: str) -> FetchResult:
        return await (self.pdfs if is_pdf_url(url) else self.pages).fetch(url)

    async def aclose(self) -> None:
        close = getattr(self.pages, "aclose", None)
        if close:
            await close()
