"""The knowledge base: saved pages cut into chunks, searched by words, cited by page.

This is the lexical half of retrieval. It needs no model and no embeddings, so it costs nothing
to run and every hit points at the exact page and text. Facts and services stay in the graph;
this holds the rest of what a citizen may ask (a phone number, an address, an office).

    python -m app.core.knowledge.chunks --ingest            # chunk every saved page
    python -m app.core.knowledge.chunks "oneday service phone number"
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from app.core.acquisition.discover import strip_menus

VERSION = 2      # bump when chunking changes, so saved pages are cut again
TARGET = 900     # characters per chunk, about
MIN_CHARS = 40   # a chunk shorter than this carries no answer

_HEADING = re.compile(r"^\s*(#{1,6})\s+(.*\S)\s*$")
_BOLD_HEADING = re.compile(r"^\s*\*\*([^*\n]{3,100})\*\*\s*$")
_LINK = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
_PAGE_MARK = re.compile(r"^Page\s+(\d+)$", re.I)   # the PDF reader's own page markers

# Words a person uses and the page may write differently. Used to widen a search, never to answer.
SYNONYMS = {
    "phone": ["telephone", "tel", "call", "contact"], "telephone": ["phone", "tel", "contact"],
    "number": ["no"], "address": ["road", "rd", "located", "street"],
    "email": ["e-mail", "mail"], "fee": ["fees", "charge", "charges", "rs"],
    "office": ["branch", "division", "unit"], "hours": ["time", "weekdays", "a.m"],
}
STOP = {"the", "a", "an", "of", "to", "for", "in", "on", "is", "are", "what", "how", "do", "i",
        "my", "me", "can", "get", "where", "and", "or", "with", "from", "at", "by", "it"}


@dataclass
class Chunk:
    position: int
    heading: str
    text: str


def _plain(line: str) -> str:
    """Keep link text, drop the URL, so a phone number is not buried in markup."""
    line = _LINK.sub(lambda m: m.group(1).strip(), line)
    line = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)
    return re.sub(r"[ \t]+", " ", line.replace("&nbsp", " ").replace("\xa0", " ")).rstrip()


def chunk_page(md: str) -> tuple[str, list[Chunk]]:
    """(page title, chunks). A chunk never crosses a heading, and a table row is never split."""
    lines = [_plain(l) for l in strip_menus(md).splitlines()]
    title = ""
    heading = ""
    buf: list[str] = []
    out: list[Chunk] = []

    def flush() -> None:
        text = "\n".join(l for l in buf if l.strip()).strip()
        buf.clear()
        if len(text) >= MIN_CHARS:
            out.append(Chunk(len(out), heading, text))

    for line in lines:
        m = _HEADING.match(line) or None
        b = _BOLD_HEADING.match(line)
        if m or b:
            flush()
            heading = (m.group(2) if m else b.group(1)).strip(" *#")
            if _PAGE_MARK.match(heading):
                heading = f"page {_PAGE_MARK.match(heading).group(1)}"   # a marker, not a title
            else:
                title = title or heading
            continue
        buf.append(line)
        if sum(len(x) + 1 for x in buf) >= TARGET and not line.lstrip().startswith("|") and not line.strip():
            flush()
    flush()
    # a very long section with no blank line: split on size at a line boundary
    final: list[Chunk] = []
    for c in out:
        if len(c.text) <= TARGET * 2:
            final.append(Chunk(len(final), c.heading, c.text))
            continue
        piece: list[str] = []
        for line in c.text.split("\n"):
            piece.append(line)
            if sum(len(x) + 1 for x in piece) >= TARGET:
                final.append(Chunk(len(final), c.heading, "\n".join(piece)))
                piece = []
        if piece and len("\n".join(piece)) >= MIN_CHARS:
            final.append(Chunk(len(final), c.heading, "\n".join(piece)))
    return title, final


# ------------------------------------------------------------------- database
def _title_from_url(url: str) -> str:
    name = url.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"[%_]20|[_-]+", " ", name.rsplit(".", 1)[0]).strip() or url


def ingest(dsn: str, crawl: Path, seeds_agency: dict[str, str]) -> dict:
    """Chunk the newest saved copy of every page. A page whose text has not changed is skipped."""
    import psycopg

    state = {}
    for f in (crawl / "state").glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        state[f.stem] = d
    newest: dict[str, Path] = {}
    for md in sorted((crawl / "archive").glob("*/*.md")):   # oldest first, so the last wins
        newest[md.stem] = md
    report = {"pages": 0, "chunks": 0, "skipped": 0, "empty": 0}
    from app.core.acquisition import tree as linktree

    labels = {u: n.get("label", "") for u, n in linktree.load(crawl)["nodes"].items()}
    with psycopg.connect(dsn) as conn:
        for key, md in newest.items():
            d = state.get(key)
            if not d:
                continue
            url = d["url"]
            text = md.read_text(encoding="utf-8")
            page_hash = hashlib.sha256(f"{VERSION}|{text}".encode("utf-8")).hexdigest()
            have = conn.execute("SELECT max(page_hash), count(*) FROM c2.chunks WHERE source_url = %s",
                                (url,)).fetchone()
            if have[1] and have[0] == page_hash:
                report["skipped"] += 1
                continue
            title, chunks = chunk_page(text)
            if not chunks:
                report["empty"] += 1
                continue
            with conn.transaction():
                conn.execute("DELETE FROM c2.chunks WHERE source_url = %s", (url,))
                for c in chunks:
                    conn.execute(
                        """INSERT INTO c2.chunks (source_url, agency, page_title, heading, position,
                                                  text, page_hash, source_file, retrieved_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (url, seeds_agency.get(url), title or labels.get(url) or _title_from_url(url),
                         c.heading, c.position, c.text, page_hash,
                         f"{md.parent.name}/{md.name}", d["fetched_at"]))
            report["pages"] += 1
            report["chunks"] += len(chunks)
    return report


_SPELLING = {"center": "centre", "centers": "centres", "colour": "color"}


def _terms(query: str) -> list[str]:
    words = [_SPELLING.get(w, w) for w in re.findall(r"[A-Za-z0-9@.+-]+", query.lower())]
    return [w for w in words if w not in STOP and len(w) > 1]


def _or_query(words: list[str]) -> str:
    seen: list[str] = []
    for w in words:
        for x in [w, *SYNONYMS.get(w, [])]:
            x = re.sub(r"[^a-z0-9]", "", x)
            if x and x not in seen:
                seen.append(x)
    return " | ".join(seen)


def search(dsn: str, query: str, limit: int = 5) -> list[dict]:
    """Every word first; if nothing matches, any word or a known synonym of it."""
    hits = _search(dsn, "websearch", query, limit)
    if not hits:
        relaxed = _or_query(_terms(query))
        if relaxed:
            hits = _search(dsn, "to_tsquery", relaxed, limit)
    return hits


def _search(dsn: str, fn: str, query: str, limit: int) -> list[dict]:
    import psycopg

    func = "websearch_to_tsquery" if fn == "websearch" else "to_tsquery"
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            """SELECT chunk_id, source_url, agency, page_title, heading, text,
                      ts_rank_cd(tsv, q) AS rank,
                      ts_headline('english', text, q, 'MaxWords=40, MinWords=15') AS snippet,
                      retrieved_at
               FROM c2.chunks, {func}('english', %s) q
               WHERE tsv @@ q
               ORDER BY rank DESC, chunk_id LIMIT %s""".replace("{func}", func),
            (query, limit)).fetchall()
    return [{"chunk_id": r[0], "url": r[1], "agency": r[2], "title": r[3], "heading": r[4],
             "text": r[5], "score": float(r[6]), "snippet": r[7], "retrieved_at": r[8].isoformat()}
            for r in rows]


_KINDS = {"phone": "phone", "telephone": "phone", "tel": "phone", "call": "phone", "fax": "fax",
          "email": "email", "mail": "email", "address": "address", "hours": "hours", "open": "hours"}


def find_contacts(contacts: list[dict], query: str, limit: int = 6) -> list[dict]:
    """Contact items whose office, role or page name contains the words asked about.

    Exact and precise: "phone Southern office" returns that office's numbers. The page link's
    own name counts too, so "Kurunegala" finds the North West office, whose page is
    kurunegala.php.
    """
    words = [w for w in _terms(query) if w not in _KINDS and w not in {"number", "numbers", "office", "branch"}]
    kinds = {_KINDS[w] for w in _terms(query) if w in _KINDS}
    scored = []
    for c in contacts:
        slug = (c.get("page_url") or "").rsplit("/", 1)[-1].rsplit(".", 1)[0]
        hay = f"{c['label']} {slug} {c['value']}".lower()
        hits = sum(1 for w in words if w in hay)
        if words and not hits:
            continue
        if kinds and c["kind"] not in kinds:
            continue
        if not words and not kinds:
            continue
        scored.append((hits, c))
    scored.sort(key=lambda t: -t[0])
    top = scored[0][0] if scored else 0
    return [c for h, c in scored if h == top][:limit] if words else [c for _, c in scored][:limit]


def main(argv: list[str] | None = None) -> int:
    from app.core.acquisition.db import dsn_from_dotenv
    from app.core.acquisition.seeds import load_seeds

    args = sys.argv[1:] if argv is None else argv
    repo = Path(__file__).resolve().parents[6]
    c2 = repo / "components" / "c2-knowledge-graph"
    dsn = dsn_from_dotenv(repo / ".env")
    if dsn is None:
        print(f"no POSTGRES_* settings in {repo / '.env'}")
        return 2
    if "--ingest" in args:
        agency = {s.url: s.agency for s in load_seeds(c2 / "research" / "data" / "seed_urls.yaml")}
        r = ingest(dsn, c2 / "research" / "data" / "crawl", agency)
        print(f"chunked {r['pages']} page(s) into {r['chunks']} chunk(s); "
              f"{r['skipped']} unchanged, {r['empty']} with no usable text")
        return 0
    if not args:
        print('usage: python -m app.core.knowledge.chunks --ingest | "your question"')
        return 2
    question = " ".join(args)
    profiles = c2 / "research" / "data" / "agency_profile"
    contacts = [c for f in sorted(profiles.glob("*.json"))
                for c in json.loads(f.read_text(encoding="utf-8")).get("contacts", [])] if profiles.exists() else []
    found = find_contacts(contacts, question)
    if found:
        print("Contacts:")
        for c in found:
            print(f"  {c['kind']:8} {c['value']:<28} {c['label']}   ({c['source_url']})")
        print()
    for hit in search(dsn, question):
        print(f"[{hit['score']:.2f}] {hit['title'] or hit['url']}  >  {hit['heading'] or '-'}")
        print(f"    {hit['url']}")
        print("    " + " ".join(hit["snippet"].split())[:260])
    return 0


if __name__ == "__main__":
    sys.exit(main())
