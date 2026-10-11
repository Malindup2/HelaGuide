"""Link discovery: find the pages a page links to, keep the ones worth a look, score them.

Discovery never decides what is monitored. It produces candidates that carry the signals a
service page should have (a fee, a document list, a prerequisite). A person opens each one
and promotes it into seed_urls.yaml. Crawling stays polite: every fetch goes through the
same robots.txt and rate-limit wrapper as a monitoring pass.
"""

from __future__ import annotations

import hashlib
import re
from collections import deque
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import quote, urldefrag, urljoin, urlparse

from app.core.acquisition.fetch import Fetcher
from app.core.acquisition.pdf import is_pdf_url

# Not service pages: media, styles, scripts, archives, social sites, and the Sinhala and Tamil
# copies of a page (the English page is the one monitored). Extend per site as needed.
SKIP_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".ico", ".css", ".js", ".zip",
                   ".rar", ".mp4", ".mp3", ".xls", ".xlsx", ".doc", ".docx", ".ppt", ".pptx")
SKIP_PATTERNS = (
    re.compile(r"(?i)[_/-](s|t|si|ta|sinhala|tamil)\.(php|html?|aspx?)(\?|$)"),
    re.compile(r"(?i)[?&]lang=(si|ta|sin|tam)\b"),
    re.compile(r"(?i)/(si|ta|sin|tam|sinhala|tamil)(/|$|\?)"),  # a language folder
    re.compile(r"(?i)gall?[ae]ry|imagegal|videogal|photo_?gal"),
    re.compile(r"(?i)vacanc|tender|procure|recruit|circular|result"),
    re.compile(r"(?i)facebook\.|twitter\.|youtube\.|instagram\.|linkedin\."),
)

# A page is worth monitoring if it states at least one of these (ported from the research
# prototype, discover_seeds.py). The prerequisite pattern is narrower than the prototype's:
# "issued by the" and "obtained from" matched ordinary sentences ("passports are issued by
# the department", "forms can be obtained from the office"). Signals are hints for a human
# to check, not facts.
FEE_RE = re.compile(r"(?i)\b(rs\.?|lkr\.?)\s*[\d,]+(\.\d{2})?|\bfee\b|\bcharge[sd]?\b")
DOC_RE = re.compile(r"(?i)\b(document|certificate|photocopy|identity card|\bnic\b|"
                    r"birth certificate|application form)\b")
PRE_RE = re.compile(r"(?i)\b(must first|before applying|before you apply|prior to|prerequisite|"
                    r"pre-requisite|request letter|should be obtained|must be obtained|"
                    r"in order to apply)\b")


@dataclass(frozen=True)
class Link:
    url: str
    text: str = ""


@dataclass(frozen=True)
class Signals:
    has_fee: bool = False
    has_docs: bool = False
    has_prereq: bool = False

    @property
    def score(self) -> int:
        return int(self.has_fee) + int(self.has_docs) + int(self.has_prereq)

    @property
    def flags(self) -> str:
        return "".join(c if on else "-" for c, on in
                       (("F", self.has_fee), ("D", self.has_docs), ("P", self.has_prereq)))


@dataclass
class Candidate:
    url: str
    label: str
    discovered_from: str
    source_type: str = "html"
    ok: bool = False
    chars: int = 0
    signals: Signals = field(default_factory=Signals)
    error: str = ""
    duplicate_of: str = ""  # the earlier candidate whose text this page repeats


class _Anchors(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None


def extract_links(html: str, base_url: str) -> list[Link]:
    """Absolute, fragment-free http(s) links in page order, first occurrence only."""
    parser = _Anchors()
    parser.feed(html or "")
    seen: set[str] = set()
    out: list[Link] = []
    for href, text in parser.links:
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        # Some sites write paths with backslashes and spaces ("assets\\formats\\Form Eng.pdf").
        href = href.strip().replace("\\", "/")
        url = urldefrag(urljoin(base_url, href))[0]
        url = quote(url, safe=":/?&=%#+,;@!$'()*~[]-._")
        if urlparse(url).scheme not in ("http", "https") or url in seen:
            continue
        seen.add(url)
        out.append(Link(url, text))
    return out


def _site(host: str | None) -> str:
    host = (host or "").lower()
    return host[4:] if host.startswith("www.") else host


def wanted(link: Link, page_url: str, extra_skip: tuple[re.Pattern, ...] = ()) -> bool:
    """Same site as the page it was found on, and not obviously not a service page."""
    if _site(urlparse(link.url).hostname) != _site(urlparse(page_url).hostname):
        return False
    path = urlparse(link.url).path.lower()
    if path.endswith(SKIP_EXTENSIONS):
        return False
    if link.url.rstrip("/") == page_url.rstrip("/"):
        return False
    # The label counts too: "pages_e.php?id=46" says nothing, but its link text says Vacancies.
    target = f"{link.url} {link.text}"
    return not any(p.search(target) for p in (*SKIP_PATTERNS, *extra_skip))


_MENU_LINE = re.compile(r"^\s*([*+-]|\d+\.)?\s*(!?\[[^\]]*\]\([^)]*\)\s*)+$")


def strip_menus(text: str) -> str:
    """Drop lines that are only links or images: the site menu and footer.

    Every page on a site repeats its menu, and a menu says "certificate" or "fee" on every
    page. Without this, each page appears to state documents. Body text, including numbered
    document lists, is kept.
    """
    return "\n".join(line for line in text.splitlines() if not _MENU_LINE.match(line))


def score_text(text: str) -> Signals:
    body = strip_menus(text)
    return Signals(bool(FEE_RE.search(body)), bool(DOC_RE.search(body)), bool(PRE_RE.search(body)))


async def discover(
    start_url: str,
    fetcher: Fetcher,
    *,
    depth: int = 1,
    limit: int = 40,
    screen: bool = True,
    known: set[str] | None = None,
    extra_skip: tuple[re.Pattern, ...] = (),
) -> list[Candidate]:
    """Breadth-first from start_url, up to `depth` link levels and `limit` candidates.

    known: URLs already registered, which are skipped. With screen=False links are only
    listed; with screen=True each candidate is fetched and scored for fee, document and
    prerequisite signals.
    """
    known = set(known or ())
    seen = {start_url} | known
    found: list[Candidate] = []
    queue: deque[tuple[str, int]] = deque([(start_url, 0)])
    fetched: dict[str, object] = {}  # one request per URL within a discovery call

    async def get(url: str):
        if url not in fetched:
            fetched[url] = await fetcher.fetch(url)
        return fetched[url]

    while queue and len(found) < limit:
        page_url, level = queue.popleft()
        page = await get(page_url)
        if not page.ok:
            if level == 0:
                raise RuntimeError(f"could not fetch the start page: {page.error}")
            continue
        for link in extract_links(page.html, page_url):
            if link.url in seen or not wanted(link, page_url, extra_skip):
                continue
            seen.add(link.url)
            cand = Candidate(link.url, link.text, page_url,
                             "pdf" if is_pdf_url(link.url) else "html")
            found.append(cand)
            if level + 1 < depth and cand.source_type == "html":
                queue.append((link.url, level + 1))
            if len(found) >= limit:
                break

    if screen:
        seen_text: dict[str, str] = {}
        for cand in found:
            got = await get(cand.url)
            cand.ok, cand.error = got.ok, got.error
            if got.ok:
                cand.chars = len(got.text)
                cand.signals = score_text(got.text)
                digest = hashlib.sha256(got.text.encode("utf-8", "ignore")).hexdigest()
                if got.text.strip() and digest in seen_text:
                    cand.duplicate_of = seen_text[digest]
                else:
                    seen_text.setdefault(digest, cand.url)
    return found
