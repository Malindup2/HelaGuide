"""An agency's contact details and form links, read from its own pages without a model.

Contacts are not services and forms are not facts about a fee, so neither goes through the
fact review. Both are taken from saved pages by plain parsing, each item keeps the page it came
from and the line it was read from, and the result is written to a JSON file before it is put
in the graph, so what went in can always be inspected.

    (Agency) -[:HAS_CONTACT]->  (Contact {kind, label, value, evidence, source_url})
    (Agency) -[:PUBLISHES_FORM]-> (Form {form_url, label, section, source_url})

No personal names are kept: a contact is an office or a role, not a person.

    python -m app.core.graph.profile --agency "Department for Registration of Persons" \\
        --contact https://www.drp.gov.lk/en/contact.php \\
        --downloads https://www.drp.gov.lk/en/downloads.php [--write]
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

_PHONE = re.compile(r"\(?0\d{1,2}\)?[\s-]?\d[\d\s-]{5,12}\d")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_FILE_EXT = (".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg", ".xls", ".xlsx")


# --------------------------------------------------------------------- helpers
class _Tables(HTMLParser):
    """Rows of every table: each cell is its text lines and its links."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[dict]]] = []
        self._row: list[dict] | None = None
        self._cell: dict | None = None
        self._href: str | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = {"text": [], "links": []}
        elif tag == "br" and self._cell is not None:
            self._cell["text"].append("\n")
        elif tag == "a" and self._cell is not None:
            self._href = a.get("href")
            self._cell["links"].append({"href": self._href, "text": ""})

    def handle_data(self, data):
        if self._cell is not None:
            self._cell["text"].append(data)
            if self._href is not None and self._cell["links"]:
                self._cell["links"][-1]["text"] += data

    def handle_endtag(self, tag):
        if tag == "a":
            self._href = None
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            raw = "".join(self._cell["text"])
            self._cell["lines"] = [" ".join(x.split()) for x in raw.split("\n") if x.strip()]
            self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None and self.tables:
            self.tables[-1].append(self._row)
            self._row = None


def _tables(html: str) -> list[list[list[dict]]]:
    p = _Tables()
    p.feed(html or "")
    return p.tables


def _clean(s: str) -> str:
    return " ".join((s or "").replace("\xa0", " ").replace("&nbsp", " ").split())


def _phones(lines: list[str] | str) -> list[str]:
    """Phone numbers, one pattern match per line so two numbers in a cell stay two numbers."""
    seen, out = set(), []
    if isinstance(lines, str):
        lines = [lines]
    for m in (x for line in lines for x in _PHONE.findall(line or "")):
        v = _clean(m)
        digits = re.sub(r"\D", "", v)
        if 9 <= len(digits) <= 11 and digits not in seen:
            seen.add(digits)
            out.append(v)
    return out


# --------------------------------------------------------------------- contacts
def parse_contacts(html: str, md: str, page_url: str) -> list[dict]:
    items: list[dict] = []

    def add(kind, label, value, quote, scope="department", link=None):
        items.append({"kind": kind, "label": label, "value": value, "evidence": _clean(quote)[:300],
                      "scope": scope, "page_url": link, "source_url": page_url})

    text = md or ""
    m = re.search(r"between\s+([\d.:]+\s*a\.m\.)\s+and\s+([\d.:]+\s*p\.m\.)\s+on\s+weekdays", text, re.I)
    if m:
        add("hours", "Call centre hours", f"{m.group(1)} to {m.group(2)}, weekdays", m.group(0))

    in_phone = False
    for line in text.splitlines():
        if re.match(r"\s*Telephone\s*:", line):
            in_phone = True
            continue
        if in_phone:
            mm = re.match(r"\s*\*\s*(.+?)\s*:\s*(\(?0[\d\s()-]+\d)\s*$", line)
            if mm:
                add("phone", _clean(mm.group(1)), _clean(mm.group(2)), line)
                continue
            if line.strip() and not line.strip().startswith("*"):
                in_phone = False
        mf = re.match(r"\s*Fax\s*:\s*(\(?0[\d\s()-]+\d)", line)
        if mf and not any(i["kind"] == "fax" and i["scope"] == "department" for i in items):
            add("fax", "Fax", _clean(mf.group(1)), line)
        me = re.match(r"\s*e-?mail\s*:\s*(" + _EMAIL.pattern + ")", line, re.I)
        if me and not any(i["kind"] == "email" and i["scope"] == "department" for i in items):
            add("email", "Email", me.group(1), line)

    addr = re.search(r"\n(Department for Registration of Persons,?\s*\n\s*[^\n]+\n\s*[^\n]+\n\s*[^\n]+)", text)
    if addr:
        parts = [_clean(x) for x in addr.group(1).split("\n") if x.strip()]
        add("address", "Head office address", " ".join(parts).rstrip(" ,.") + ".", " ".join(parts))

    # The page's own markup loses a location cell in one provincial row, so take the office
    # names and page links from the Markdown, in order.
    prov = re.findall(r"\n\s*(Provincial [Oo]ffice[^\n\]]*?)\s*\]\((https?://[^)\s]+)\)", text)
    prov_i = 0
    for rows in _tables(html):
        if not rows or len(rows) < 2:
            continue
        head = " ".join(" ".join(c["lines"]) for c in rows[0]).lower()
        if "telephone" not in head:
            continue
        provincial = "provincial" in head or "location" in head
        for row in rows[1:]:
            if len(row) < 5:
                continue
            name_cell = row[1]
            if provincial and len(row) == 5:      # location cell missing in the page markup
                row = row[:2] + [{"lines": [], "links": []}] + row[2:]
            title = name_cell["lines"][1] if len(name_cell["lines"]) > 1 else ""
            branches = [_clean(l["text"]) for l in name_cell["links"] if _clean(l["text"])]
            if provincial:
                loc = row[2]
                links = loc["links"]
                office = _clean(" ".join(l for l in loc["lines"]) or "")
                page = next((urljoin(page_url, l["href"]) for l in links
                             if l["href"] and "google." not in l["href"]), None)
                if prov_i < len(prov):
                    office, page = _clean(prov[prov_i][0]) or office, prov[prov_i][1]
                prov_i += 1
                label = office or title or "Provincial office"
                cols = row[3:]
            else:
                label = ", ".join(branches) or title or "Head office"
                if title and branches:
                    label = f"{title} ({', '.join(branches)})"
                page = next((urljoin(page_url, l["href"]) for c in (name_cell,) for l in c["links"]
                             if l["href"]), None)
                cols = row[2:]
            if len(cols) < 3:
                continue
            quote = f"{label} | " + " | ".join(" ".join(c["lines"]) for c in cols)
            for ph in _phones(cols[0]["lines"]):
                add("phone", label, ph, quote, "provincial" if provincial else "branch", page)
            for ph in _phones(cols[1]["lines"]):
                add("fax", label, ph, quote, "provincial" if provincial else "branch", page)
            for em in _EMAIL.findall(" ".join(cols[2]["lines"])):
                add("email", label, em, quote, "provincial" if provincial else "branch", page)
    items += _more_contacts(html, md, page_url, items)
    return items


_LABELLED = re.compile(r"^\s*[*_]*\s*(hotline|phone|telephone|tel(?:\.| no\.?)?|fax|e-?mail)\s*[*_]*\s*:?\s*[*_]*\s*:?\s*(.+?)\s*$", re.I)
_BOLD = re.compile(r"^\s*\*\*([^*\n]{3,110})\*\*\s*$")
_LABEL_WORDS = re.compile(r"(?i)^(telephone|tel|phone|fax|e-?mail|email|web ?site|hotline|contact details)")


def _more_contacts(html: str, md: str, page_url: str, have: list[dict]) -> list[dict]:
    """The other common layouts: a block of `Hotline : 1962` lines, a two-column table of
    "topic | number", and role blocks (a bold title followed by Telephone, Fax, Email)."""
    out: list[dict] = []
    seen = {(i["kind"], i["label"], i["value"]) for i in have}

    def add(kind, label, value, quote, scope="department"):
        key = (kind, label, value)
        if key in seen or not value:
            return
        seen.add(key)
        out.append({"kind": kind, "label": label, "value": value, "evidence": _clean(quote)[:300],
                    "scope": scope, "page_url": None, "source_url": page_url})

    kind_of = {"hotline": "phone", "phone": "phone", "telephone": "phone", "tel": "phone",
               "tel no": "phone", "tel.": "phone", "fax": "fax", "email": "email", "e-mail": "email"}
    # 1. role blocks and top-of-page labelled lines, read in order
    role = None
    for line in (md or "").splitlines():
        b = _BOLD.match(line)
        if b and not _LABEL_WORDS.match(b.group(1)):
            role = _clean(b.group(1)).rstrip(":")
            continue
        m = _LABELLED.match(line)
        if not m:
            continue
        word = m.group(1).lower().rstrip(".")
        kind, val = kind_of.get(word, kind_of.get(word.replace(" no", ""), None)), _clean(m.group(2)).strip("*_ ")
        if not kind:
            continue
        if kind == "email":
            e = _EMAIL.search(val)
            val = e.group(0) if e else ""
        else:
            ph = _phones(val) or ([val] if re.fullmatch(r"\+?[\d\s()-]{4,}", val) else [])
            val = ph[0] if ph else ""
        label = "Hotline" if word == "hotline" else (role or "Department")
        add(kind, label, val, line, "branch" if role else "department")

    # 1b. phone numbers written as tel: links under a label or role ("General Lines:", "Fax:")
    label = ""
    person = re.compile(r"^(mrs?|ms|miss|dr|prof|rev|hon)\.?", re.I)
    for line in (md or "").splitlines():
        text = _clean(re.sub(r"\(tel:[^)]*\)|\(mailto:[^)]*\)", "", line))
        text = _clean(re.sub(r"[\[\]#*_]+", " ", text))
        tels = re.findall(r"\[([^\]]+)\]\(tel:[^)]+\)", line)
        # lines that start with their own label ("Fax : ...") and table rows are read above
        own = _LABELLED.match(line) or line.lstrip().startswith("|")
        plain = [] if own else _phones(re.sub(r"\[[^\]]*\]\([^)]*\)", "", line))
        if tels or plain:
            lab = label or "Department"
            for n in [_clean(t) for t in tels] + plain:
                kind = "fax" if "fax" in lab.lower() else "phone"
                add(kind, lab, n, f"{lab}: {n}", "branch")
            continue
        if not text or text.startswith("!") or "protected from spambots" in text:
            continue
        if line.lstrip().startswith("#") or text.endswith(":") or (len(text) < 70 and not person.match(text)):
            label = text.rstrip(":").strip()

    # 2. two-column tables: topic | number(s)
    for rows in _tables(html):
        for row in rows:
            if len(row) != 2:
                continue
            topic = _clean(" ".join(row[0]["lines"]))
            nums = _phones(row[1]["lines"]) or _phones(" / ".join(row[1]["lines"]).split("/"))
            if topic and nums and len(topic) > 6 and not _PHONE.search(topic):
                for n in nums:
                    add("phone", topic, n, f"{topic} | {' / '.join(row[1]['lines'])}", "topic")
    return out


# ------------------------------------------------------------------------ forms
def parse_forms(md: str, page_url: str) -> list[dict]:
    """Rows of the form `| label | [](file url) |`, under the heading they sit below."""
    out: list[dict] = []
    seen: set[str] = set()
    section = "forms"
    for line in (md or "").splitlines():
        if re.match(r"\s*#+\s*\**\s*Acts", line, re.I):
            section = "acts"
        elif re.match(r"\s*#+\s*\**\s*Forms", line, re.I):
            section = "forms"
        m = re.match(r"\s*\|\s*(?:&nbsp;?)?\s*(.+?)\s*\|\s*\[[^\]]*\]\(([^)\s]+)\)\s*\|", line)
        if not m:
            continue
        label, url = _clean(m.group(1)), urljoin(page_url, m.group(2))
        if not url.lower().split("?")[0].endswith(_FILE_EXT) or url in seen:
            continue  # a link back to the page itself is not a file
        seen.add(url)
        out.append({"label": label, "form_url": url, "section": section, "source_url": page_url})
    return out


# ------------------------------------------------------------------------ graph
def _agency_id(name: str) -> str:
    from app.core.graph.writer import _agency_id as agency_id

    return agency_id(name)


def write_graph(driver, agency: str, contacts: list[dict], forms: list[dict]) -> dict:
    aid = _agency_id(agency)
    with driver.session() as session:
        session.run("MERGE (a:Agency {agency_id: $aid}) ON CREATE SET a.name = $name",
                    aid=aid, name=agency).consume()
        for c in contacts:
            key = hashlib.sha256(f"{aid}|{c['kind']}|{c['label']}|{c['value']}".encode()).hexdigest()[:16]
            session.run(
                """MATCH (a:Agency {agency_id: $aid})
                   MERGE (c:Contact {contact_key: $key})
                   SET c.kind = $kind, c.label = $label, c.value = $value, c.scope = $scope,
                       c.evidence = $evidence, c.source_url = $src, c.page_url = $page
                   MERGE (a)-[:HAS_CONTACT]->(c)""",
                aid=aid, key=key, kind=c["kind"], label=c["label"], value=c["value"],
                scope=c["scope"], evidence=c["evidence"], src=c["source_url"],
                page=c.get("page_url")).consume()
        for f in forms:
            session.run(
                """MATCH (a:Agency {agency_id: $aid})
                   MERGE (x:Form {form_url: $url})
                   SET x.label = coalesce(x.label, $label), x.section = $section,
                       x.source_url = $src
                   MERGE (a)-[:PUBLISHES_FORM]->(x)""",
                aid=aid, url=f["form_url"], label=f["label"], section=f["section"],
                src=f["source_url"]).consume()
    return {"agency_id": aid, "contacts": len(contacts), "forms": len(forms)}


def _saved(crawl: Path, url: str, ext: str) -> str:
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    files = sorted(crawl.glob(f"archive/*/{key}.{ext}"))
    if not files:
        raise FileNotFoundError(f"{url} has not been saved yet (no archive/*/{key}.{ext})")
    return files[-1].read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agency", required=True)
    ap.add_argument("--contact", help="URL of the saved contact page")
    ap.add_argument("--downloads", help="URL of the saved downloads page")
    ap.add_argument("--write", action="store_true", help="write to the graph (default: show only)")
    args = ap.parse_args(argv)

    from app.core.graph.writer import neo4j_from_dotenv

    repo = Path(__file__).resolve().parents[6]
    crawl = repo / "components/c2-knowledge-graph/research/data/crawl"
    contacts: list[dict] = []
    forms: list[dict] = []
    if args.contact:
        contacts = parse_contacts(_saved(crawl, args.contact, "html"), _saved(crawl, args.contact, "md"),
                                  args.contact)
    if args.downloads:
        forms = parse_forms(_saved(crawl, args.downloads, "md"), args.downloads)

    profile = {"agency": args.agency, "contacts": contacts, "forms": forms}
    out = repo / "components/c2-knowledge-graph/research/data/agency_profile"
    out.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^a-z0-9]+", "_", args.agency.lower()).strip("_")
    (out / f"{name}.json").write_text(json.dumps(profile, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{args.agency}: {len(contacts)} contact item(s), {len(forms)} form link(s) -> {out / (name + '.json')}")
    for c in contacts:
        print(f"  {c['kind']:8} {c['label'][:55]:55} {c['value']}")
    for f in forms:
        print(f"  {f['section']:6} {f['label'][:70]:70} {f['form_url'].rsplit('/', 1)[-1]}")
    if args.write:
        conf = neo4j_from_dotenv(repo / ".env")
        if conf is None:
            print("no NEO4J_PASSWORD in .env")
            return 2
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(conf[0], auth=(conf[1], conf[2]))
        try:
            print("written:", write_graph(driver, args.agency, contacts, forms))
        finally:
            driver.close()
    else:
        print("\n(not written: add --write to put these in the graph)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
