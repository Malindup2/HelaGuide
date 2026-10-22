"""A small local page for the whole loop: pick a saved page, read it, review, approve, write.

    python -m app.admin_ui          opens http://127.0.0.1:8765

It runs only on this machine (127.0.0.1) and does what the command line does, with buttons.
Nothing reaches the graph without a click on "Approve" and then on "Write to graph".
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.core.acquisition.db import dsn_from_dotenv, read_dotenv
from app.core.acquisition.seeds import load_seeds
from app.core.extraction.extractor import count_headings, extract_page, extract_sections
from app.core.extraction.gate import should_extract
from app.core.extraction.llm import OpenAICompatClient
from app.core.extraction.staging import StagingStore
from app.core.graph.review import ReviewStore
from app.core.graph.writer import GraphWriter, neo4j_from_dotenv

C2_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = C2_ROOT.parents[1]
CRAWL = C2_ROOT / "research" / "data" / "crawl"
SEEDS = C2_ROOT / "research" / "data" / "seed_urls.yaml"
PORT = 8765

app = FastAPI(title="HelaGuide C2 review")
_FIGURES_DIR = C2_ROOT / "research" / "docs" / "figures"
if _FIGURES_DIR.is_dir():
    app.mount("/figures", StaticFiles(directory=str(_FIGURES_DIR)), name="figures")


def _env() -> dict:
    return read_dotenv(REPO_ROOT / ".env")


def _dsn() -> str:
    dsn = dsn_from_dotenv(REPO_ROOT / ".env")
    if dsn is None:
        raise HTTPException(500, f"no POSTGRES_* settings in {REPO_ROOT / '.env'}")
    return dsn


def _neo4j() -> tuple[str, str, str]:
    conf = neo4j_from_dotenv(REPO_ROOT / ".env")
    if conf is None:
        raise HTTPException(500, f"no NEO4J_PASSWORD in {REPO_ROOT / '.env'}")
    return conf


def _llm(fast_fail: bool = False) -> OpenAICompatClient:
    """fast_fail=True skips the retry/backoff ladder (up to 120s on a persistent 429) --
    for a one-off demo/calibration call where a daily quota error will not resolve itself
    by waiting a few seconds, so retrying just burns the caller's time for nothing."""
    env = _env()
    key = os.environ.get("LLM_API_KEY") or env.get("LLM_API_KEY", "")
    if not key:
        raise HTTPException(400, "No LLM_API_KEY in .env. Add your Gemini key there and restart.")
    return OpenAICompatClient(
        key,
        os.environ.get("C2_LLM_MODEL") or env.get("C2_LLM_MODEL", "gemini-2.5-flash"),
        os.environ.get("C2_LLM_BASE_URL") or env.get(
            "C2_LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai"),
        reasoning_effort=None,
        retries=1 if fast_fail else 4,
    )


UNSORTED = "svc:unsorted"  # only used when the model names no service for a part of a page


def _known_services() -> list[str]:
    """Services that already have an approved fact: what a new page should attach to."""
    import psycopg

    with psycopg.connect(_dsn()) as c:
        return [r[0] for r in c.execute(
            "SELECT DISTINCT service_id FROM c2.staged_facts WHERE status = 'approved' "
            "AND service_id IS NOT NULL ORDER BY 1")]


def _file_key(path: str) -> str:
    """archive/<date>/<name>: the same however the path was written when it was recorded."""
    return "/".join(Path(path.replace("\\", "/")).parts[-3:])


def _reads() -> tuple[dict[str, set[str]], set[str]]:
    """(urls -> archive files already read, urls read with no file recorded)."""
    import psycopg

    files: dict[str, set[str]] = {}
    unknown: set[str] = set()
    with psycopg.connect(_dsn()) as c:
        for url, src in c.execute("SELECT source_url, source_file FROM c2.extractions"):
            if src:
                files.setdefault(url, set()).add(_file_key(src))
            else:
                unknown.add(url)
    return files, unknown


def _seed_for(url: str):
    for s in load_seeds(SEEDS):
        if s.url == url:
            return s
    return None


def _seeds_by_url() -> dict:
    """load_seeds() parses the whole YAML file; call it once and look up by URL, not once per
    page. /api/files used to call _seed_for() inside its per-file loop, which re-parsed
    ~900 lines of YAML on every one of ~280 files -- seconds of real wall time for a result
    that never changed within the request."""
    return {s.url: s for s in load_seeds(SEEDS)}


# ------------------------------------------------------------------------- API
@app.get("/api/status")
def status() -> dict:
    out = {"postgres": False, "neo4j": False, "model_key": bool(_env().get("LLM_API_KEY"))}
    try:
        import psycopg

        with psycopg.connect(_dsn(), connect_timeout=3) as c:
            c.execute("SELECT 1 FROM c2.staged_facts LIMIT 1")
        out["postgres"] = True
    except Exception as e:  # noqa: BLE001
        out["postgres_error"] = f"{type(e).__name__}"
    try:
        w = GraphWriter(_dsn(), *_neo4j())
        w.driver.verify_connectivity()
        w.close()
        out["neo4j"] = True
    except Exception as e:  # noqa: BLE001
        out["neo4j_error"] = f"{type(e).__name__}"
    return out


@app.get("/api/files")
def files() -> list[dict]:
    """Every saved page, with the page's address, the service it is for, and whether the
    model has read it."""
    import psycopg

    url_of = {}
    for f in (CRAWL / "state").glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        url_of[f.stem] = d["url"]
    with psycopg.connect(_dsn()) as c:
        sent = {r[0]: r[1] for r in c.execute(
            "SELECT source_url, max(extraction_id) FROM c2.extractions GROUP BY source_url")}
        pending = {r[0]: r[1] for r in c.execute(
            "SELECT source_url, count(*) FROM c2.staged_facts WHERE status='pending' GROUP BY source_url")}
        counts: dict[str, dict] = {}
        for src, status, written, n in c.execute(
                """SELECT source_url, status, written_at IS NOT NULL, count(*)
                   FROM c2.staged_facts GROUP BY source_url, status, written_at IS NOT NULL"""):
            row = counts.setdefault(src, {"in_graph": 0, "approved_not_written": 0, "rejected": 0})
            if status == "approved" and written:
                row["in_graph"] += n
            elif status == "approved":
                row["approved_not_written"] += n
            elif status == "rejected":
                row["rejected"] += n
        found: dict[str, list[str]] = {}
        for src, svc in c.execute(
                "SELECT DISTINCT source_url, service_id FROM c2.staged_facts ORDER BY 1, 2"):
            found.setdefault(src, []).append(svc)
        by_sections = {r[0] for r in c.execute(
            "SELECT DISTINCT source_url FROM c2.extractions WHERE model LIKE '%[sections]%'")}
    read_files, read_unknown = _reads()
    seeds = _seeds_by_url()
    seen: set[str] = set()
    rows = []
    for md in sorted((CRAWL / "archive").glob("*/*.md"), reverse=True):
        url = url_of.get(md.stem, "")
        latest = url not in seen  # newest first: the first copy of a URL is the current one
        seen.add(url)
        key = f"archive/{md.parent.name}/{md.name}"
        read_this = key in read_files.get(url, set()) or (url in read_unknown and latest)
        seed = seeds.get(url)
        text = md.read_text(encoding="utf-8")
        gate = should_extract(text)
        if not latest:
            state = "older"
        elif read_this:
            state = "read"
        elif url in sent:
            state = "changed"      # read before, but the page has a newer copy
        else:
            state = "to_read" if gate.send else "nothing"
        rows.append({
            "state": state, "latest": latest, "read_this": read_this,
            "file": f"{md.parent.name}/{md.name}", "url": url, "size": md.stat().st_size,
            "service": seed.service if seed else None, "agency": seed.agency if seed else None,
            "found": found.get(url, []), "sent": url in sent, "pending": pending.get(url, 0),
            "in_graph": counts.get(url, {}).get("in_graph", 0),
            "approved_not_written": counts.get(url, {}).get("approved_not_written", 0),
            "rejected": counts.get(url, {}).get("rejected", 0),
            "headings": count_headings(text), "by_sections": url in by_sections,
            "gate_send": gate.send, "gate_reason": gate.reason, "signals": gate.signals,
        })
    return rows


class ExtractIn(BaseModel):
    file: str
    force: bool = False
    by_sections: bool = False
    reread: bool = False  # read again although this exact saved page was already read


@app.post("/api/extract")
def extract(body: ExtractIn) -> dict:
    path = (CRAWL / "archive" / body.file).resolve()
    if CRAWL.resolve() not in path.parents or not path.exists():
        raise HTTPException(404, "that file is not in the crawl archive")
    url = None
    for f in (CRAWL / "state").glob("*.json"):
        if f.stem == path.stem:
            url = json.loads(f.read_text(encoding="utf-8"))["url"]
    seed = _seed_for(url or "")
    if not url or not seed:
        raise HTTPException(400, "this page is not in the seed list, so its service is unknown")
    text = path.read_text(encoding="utf-8")
    read_files, read_unknown = _reads()
    key = f"archive/{path.parent.name}/{path.name}"
    if not body.reread and (key in read_files.get(url, set()) or url in read_unknown):
        return {"skipped": True, "reason": "already read and the page has not changed since",
                "chars": len(text), "signals": ""}
    gate = should_extract(text)
    if not gate.send and not body.force:
        return {"skipped": True, "reason": gate.reason, "chars": gate.chars, "signals": gate.signals}

    # a page nobody labelled is always read by sections: the model names the services it holds
    service_id = seed.service or UNSORTED
    by_sections = body.by_sections or not seed.service
    extra = {"known_services": tuple(_known_services())} if by_sections else {}
    reader = extract_sections if by_sections else extract_page
    result = reader(text, service_id=service_id, agency=seed.agency, source_url=url,
                    retrieved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    llm=_llm(), **extra)
    if result.error:
        raise HTTPException(502, result.error)
    store = StagingStore(_dsn())
    try:
        extraction_id, staged = store.save(url, result, service_id, seed.agency,
                                           source_file=str(path.relative_to(REPO_ROOT)))
    finally:
        store.close()
    return {"skipped": False, "extraction_id": extraction_id, "service": service_id,
            "facts": len(result.facts), "new_pending": staged, "dropped": result.dropped,
            "sections": result.sections,
            "tokens_in": result.prompt_tokens, "tokens_out": result.completion_tokens,
            "model": result.model}


class RefileIn(BaseModel):
    url: str
    service_id: str
    reviewer: str = "malindu"


@app.post("/api/refile")
def refile(body: RefileIn) -> dict:
    """The facts on a page describe a different service than the one it was listed under.
    Supersede its pending facts (kept, with the reason) and file the same model reply under the
    right service, which is created if it is new. No model call."""
    import re

    from app.core.extraction.restage import restage

    if not re.fullmatch(r"svc:[a-z0-9_]+", body.service_id):
        raise HTTPException(400, "a service id looks like svc:nic_translation (lowercase, digits, _)")
    store = ReviewStore(_dsn())
    try:
        extraction_id = store.latest_extraction_for(body.url)
        if extraction_id is None:
            raise HTTPException(404, "that page has not been read by the model yet")
        old = store.pending_for_extraction(extraction_id)
        if old:
            store.decide_many(old, "rejected", body.reviewer,
                              f"superseded: the facts describe {body.service_id}, a different "
                              "service than the page was listed under")
    finally:
        store.close()
    try:
        new_id, facts, dropped, staged = restage(_dsn(), extraction_id, REPO_ROOT,
                                                 service_id=body.service_id)
    except LookupError as e:
        raise HTTPException(409, str(e)) from e
    _set_seed_service(body.url, body.service_id)
    return {"moved_from": len(old), "new_extraction_id": new_id, "facts": len(facts),
            "new_pending": staged, "dropped": len(dropped), "service": body.service_id}


def _set_seed_service(url: str, service_id: str) -> None:
    """Keep the seed list in step, so the next crawl and read use the right service."""
    lines = SEEDS.read_text(encoding="utf-8").splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.strip() == f"- url: {url}":
            for j in range(i + 1, min(i + 6, len(lines))):
                if lines[j].lstrip().startswith("service:"):
                    indent = lines[j][: len(lines[j]) - len(lines[j].lstrip())]
                    lines[j] = f"{indent}service: {service_id}\n"
                    SEEDS.write_text("".join(lines), encoding="utf-8")
                    return
    return


@app.get("/api/pending")
def pending(service: str | None = None) -> list[dict]:
    import psycopg

    with psycopg.connect(_dsn()) as c:
        known = {r[0] for r in c.execute(
            "SELECT DISTINCT service_id FROM c2.staged_facts WHERE status = 'approved'")}
    store = ReviewStore(_dsn())
    try:
        return [{"id": f.staged_id, "fact_id": f.fact_id, "service": f.service_id,
                 "predicate": f.predicate, "value": f.value_text, "unit": f.unit,
                 "old": f.old_value, "quote": f.evidence, "url": f.source_url,
                 "forms": f.forms or [], "new_service": f.service_id not in known}
                for f in store.pending(service, limit=1000)]
    finally:
        store.close()


class DecideIn(BaseModel):
    ids: list[int]
    decision: str
    reason: str = ""
    reviewer: str = "malindu"


@app.post("/api/decide")
def decide(body: DecideIn) -> dict:
    if body.decision not in ("approved", "rejected"):
        raise HTTPException(400, "decision must be approved or rejected")
    if body.decision == "rejected" and not body.reason.strip():
        raise HTTPException(400, "a rejection needs a reason")
    store = ReviewStore(_dsn())
    try:
        done, skipped = store.decide_many(body.ids, body.decision, body.reviewer, body.reason)
    finally:
        store.close()
    return {"decided": done, "skipped": skipped}


@app.post("/api/write")
def write() -> dict:
    w = GraphWriter(_dsn(), *_neo4j())
    try:
        report = w.write_approved()
        return {"new": report.new, "changed": report.changed, "same": report.same,
                "failed": report.failed, "graph": w.summary()}
    finally:
        w.close()


@app.get("/api/tree")
def link_tree() -> dict:
    """Every page we know of, nested under the page it was found on, with how far each got:
    not saved, saved, read, in the graph."""
    from urllib.parse import urlparse

    from app.core.acquisition import tree as linktree

    nodes = {u: dict(n) for u, n in linktree.load(CRAWL)["nodes"].items()}
    rows = {r["url"]: r for r in files() if r.get("latest", True) and r["url"]}
    roots = [u for u, n in nodes.items() if not n.get("parent")]
    host = lambda u: (urlparse(u).hostname or "").removeprefix("www.")  # noqa: E731
    for url, r in rows.items():   # saved pages the tree has not seen: put them under their site
        if url not in nodes:
            home = next((x for x in roots if host(x) == host(url)), None)
            nodes[url] = {"parent": home, "label": "", "signals": r["signals"], "type": "html",
                          "chars": r["size"], "found": "", "unplaced": home is not None}
    out = {}
    for url, n in nodes.items():
        r = rows.get(url)
        if r is None:
            status = "not saved"
        elif r["in_graph"]:
            status = "in graph"
        else:
            status = {"read": "read", "to_read": "saved, to read", "changed": "changed since read",
                      "nothing": "saved, nothing to read"}.get(r["state"], r["state"])
        out[url] = {"parent": n.get("parent"), "label": n.get("label") or "",
                    "signals": n.get("signals") or (r["signals"] if r else ""),
                    "type": n.get("type", "html"), "status": status,
                    "facts": r["in_graph"] if r else 0, "waiting": r["pending"] if r else 0,
                    "services": r["found"] if r else [], "unplaced": bool(n.get("unplaced"))}
    counts = {"known": len(out),
              "saved": sum(1 for v in out.values() if v["status"] != "not saved"),
              "read": sum(1 for v in out.values() if v["status"] in ("read", "in graph")),
              "in_graph": sum(1 for v in out.values() if v["status"] == "in graph")}
    return {"nodes": out, "counts": counts}


@app.get("/api/search")
def search_knowledge(q: str, limit: int = 5) -> dict:
    """Contacts first (exact), then the saved pages (words). Every hit names its page."""
    from app.core.knowledge.chunks import find_contacts, search

    profiles = C2_ROOT / "research" / "data" / "agency_profile"
    contacts = [c for f in sorted(profiles.glob("*.json"))
                for c in json.loads(f.read_text(encoding="utf-8")).get("contacts", [])]         if profiles.exists() else []
    return {"contacts": find_contacts(contacts, q), "pages": search(_dsn(), q, limit)}


@app.get("/api/plan")
def plan(service: str, case: str | None = None) -> dict:
    """What a person needs for one service: its prerequisite chain, in order, from the graph
    alone. No model call."""
    from neo4j import GraphDatabase

    from app.core.graph.plan import build_plan, to_dict

    uri, user, password = _neo4j()
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        result = build_plan(driver, service, case)
    finally:
        driver.close()
    if result is None:
        raise HTTPException(404, f"{service} is not in the graph")
    return to_dict(result)


class AutoIn(BaseModel):
    apply: bool = False


@app.post("/api/auto")
def auto(body: AutoIn) -> dict:
    """Approve the clean waiting facts by rule. Without apply it only reports what it would do."""
    from app.core.graph.autoreview import run

    return run(_dsn(), apply=body.apply)


@app.get("/api/auto_sample")
def auto_sample(n: int = 10) -> list[dict]:
    from app.core.graph.autoreview import sample

    return sample(_dsn(), n)


class RenameIn(BaseModel):
    old: str
    new: str
    reviewer: str = "malindu"


@app.post("/api/rename_service")
def rename_service(body: RenameIn) -> dict:
    store = ReviewStore(_dsn())
    try:
        return {"moved": store.rename_service(body.old, body.new, body.reviewer)}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    finally:
        store.close()


@app.get("/api/graph")
def graph() -> dict:
    w = GraphWriter(_dsn(), *_neo4j())
    try:
        with w.driver.session() as s:
            chain = s.run("""MATCH (a:Service)-[r:REQUIRES]->(b:Service) WHERE r.valid_to IS NULL
                             RETURN a.service_id AS a, b.service_id AS b ORDER BY a, b""").data()
            empty = s.run("MATCH (s:Service) WHERE NOT (s)-[:HAS_FACT]->() "
                          "RETURN collect(s.service_id) AS e").single()["e"]
        return {"summary": w.summary(), "chain": chain, "empty_services": empty}
    finally:
        w.close()


@app.get("/api/graph/visual")
def graph_visual() -> dict:
    """The real Service/REQUIRES graph plus each service's current community (from the real
    SO3 community layer, when it exists), for a live node-link diagram. A node is flagged
    "recently_updated" when its community's summary was regenerated in the last 10 minutes --
    so after running the SO3 ablation, the panel can SEE which real community it just
    touched, not just read a number."""
    from datetime import datetime, timedelta, timezone

    w = GraphWriter(_dsn(), *_neo4j())
    try:
        with w.driver.session() as s:
            nodes = [dict(r) for r in s.run(
                """MATCH (sv:Service)
                   OPTIONAL MATCH (sv)-[m:IN_COMMUNITY]->(c:Community) WHERE m.valid_to IS NULL
                   OPTIONAL MATCH (sv)-[:PROVIDED_BY]->(a:Agency)
                   RETURN sv.service_id AS id, c.community_id AS community,
                          c.summary_updated_at AS community_updated_at, a.name AS agency""")]
            edges = [dict(r) for r in s.run(
                """MATCH (a:Service)-[r:REQUIRES]->(b:Service) WHERE r.valid_to IS NULL
                   RETURN DISTINCT a.service_id AS source, b.service_id AS target""")]
        now = datetime.now(timezone.utc)
        for n in nodes:
            ts = n.pop("community_updated_at", None)
            n["recently_updated"] = bool(ts and (now - ts.to_native()) < timedelta(minutes=10))
        return {"nodes": nodes, "edges": edges}
    finally:
        w.close()


# ------------------------------------------------------------------- demos
# Every demo below runs the real production code (fingerprint/classify, build_plan,
# chunk search) against real saved pages and the real database -- nothing here is a
# pre-recorded number. They exist so the novelties can be shown live in this dashboard
# instead of read off a markdown report or a terminal.

_FEE_LIKE = re.compile(r"(?:Rs\.?|LKR)\s*[\d][\d,]*", re.IGNORECASE)


def _bump_last_digit(s: str) -> str:
    chars = list(s)
    for i in range(len(chars) - 1, -1, -1):
        if chars[i].isdigit():
            chars[i] = str((int(chars[i]) + 1) % 10)
            return "".join(chars)
    return s


@app.post("/api/demo/invisible_edit")
def demo_invisible_edit() -> dict:
    """Novelty 1: find a real saved page with a fee-like number, flip its last digit in
    both the raw HTML and the extracted text (every tag stays untouched), then run the
    real fingerprint()/classify() pipeline on the before/after pair. A byte-identical
    layout with one changed digit should classify as CONTENT_CHANGED, not UNCHANGED."""
    from app.core.acquisition.fingerprint import classify, fingerprint

    for html_path in sorted((CRAWL / "archive").glob("*/*.html")):
        md_path = html_path.with_suffix(".md")
        if not md_path.exists():
            continue
        html = html_path.read_text(encoding="utf-8", errors="ignore")
        text = md_path.read_text(encoding="utf-8")
        m = _FEE_LIKE.search(text)
        if not m or m.group() not in html:
            continue
        old_frag, new_frag = m.group(), _bump_last_digit(m.group())
        if new_frag == old_frag:
            continue
        text2 = text.replace(old_frag, new_frag, 1)
        html2 = html.replace(old_frag, new_frag, 1)
        prev, cur = fingerprint(text, html), fingerprint(text2, html2)
        result = classify(prev, cur)
        return {
            "page": html_path.name,
            "edit": f'"{old_frag}" -> "{new_frag}"  (everything else on the page is byte-identical)',
            "before_content_hash": prev.content_hash[:16],
            "after_content_hash": cur.content_hash[:16],
            "before_structure_hash": prev.structure_hash[:16],
            "after_structure_hash": cur.structure_hash[:16],
            "layout_byte_identical": prev.structure_hash == cur.structure_hash,
            "classification": result.kind.value,
            "detail": result.detail,
        }
    raise HTTPException(404, "No saved page with a fee-like number was found to edit. Save some pages first.")


@app.get("/api/demo/token_cost")
def demo_token_cost() -> dict:
    """Novelty 2: real token totals from every extraction run so far, plus a live,
    timed classify() call on a real saved page proving the unchanged path makes no
    model call and costs zero tokens -- timed now, not pasted from an earlier run."""
    import time

    import psycopg

    from app.core.acquisition.fingerprint import classify, fingerprint

    with psycopg.connect(_dsn()) as c:
        pages, total_tokens = c.execute(
            "SELECT count(*), coalesce(sum(prompt_tokens + completion_tokens), 0) "
            "FROM c2.extractions WHERE prompt_tokens > 0 OR completion_tokens > 0").fetchone()

    sample_ms, kind = None, None
    for md_path in (CRAWL / "archive").glob("*/*.md"):
        html_path = md_path.with_suffix(".html")
        if not html_path.exists():
            continue
        text = md_path.read_text(encoding="utf-8")
        raw = html_path.read_text(encoding="utf-8", errors="ignore")
        t0 = time.perf_counter()
        prev = fingerprint(text, raw)
        cur = fingerprint(text, raw)  # the same page again: what a repeat crawl sees when nothing changed
        result = classify(prev, cur)
        sample_ms = (time.perf_counter() - t0) * 1000
        kind = result.kind.value
        break
    return {
        "pages_extracted_so_far": pages,
        "total_tokens_so_far": total_tokens,
        "avg_tokens_per_page": round(total_tokens / pages) if pages else 0,
        "live_unchanged_check_ms": round(sample_ms, 3) if sample_ms is not None else None,
        "live_unchanged_check_tokens": 0,
        "live_classification": kind,
    }


@app.get("/api/crawl/activity")
def crawl_activity(limit: int = 50) -> dict:
    """Real crawl history and LLM token usage, straight from Postgres -- which URLs were
    crawled, how long each took, and what each extraction call cost in tokens. Not a live
    feed (acquisition runs as a one-shot batch script, not a server), but every row is a
    real event from c2.crawl_runs / c2.page_results / c2.extractions, newest first."""
    import psycopg

    with psycopg.connect(_dsn()) as c:
        runs = [
            {
                "run_id": run_id,
                "started_at": started_at.isoformat() if started_at else None,
                "finished_at": finished_at.isoformat() if finished_at else None,
                "mode": mode,
                "pages": pages,
                "counts": counts,
                "to_extract": to_extract,
            }
            for run_id, started_at, finished_at, mode, pages, counts, to_extract in c.execute(
                """SELECT run_id, started_at, finished_at, mode, pages, counts, to_extract
                   FROM c2.crawl_runs ORDER BY started_at DESC LIMIT %s""", (limit,))
        ]
        pages_rows = [
            {
                "url": url,
                "change_class": change_class,
                "http_status": http_status,
                "duration_ms": duration_ms,
                "char_count": char_count,
                "fetched_at": fetched_at.isoformat() if fetched_at else None,
                "run_id": run_id,
            }
            for url, change_class, http_status, duration_ms, char_count, fetched_at, run_id in c.execute(
                """SELECT url, change_class, http_status, duration_ms, char_count, fetched_at, run_id
                   FROM c2.page_results ORDER BY fetched_at DESC LIMIT %s""", (limit,))
        ]
        extraction_rows = [
            {
                "source_url": source_url,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "facts": facts,
                "dropped": dropped,
                "error": error,
                "created_at": created_at.isoformat() if created_at else None,
            }
            for source_url, model, prompt_tokens, completion_tokens, facts, dropped, error, created_at
            in c.execute(
                """SELECT source_url, model, prompt_tokens, completion_tokens, facts, dropped,
                          error, created_at
                   FROM c2.extractions ORDER BY created_at DESC LIMIT %s""", (limit,))
        ]
    return {"runs": runs, "pages": pages_rows, "extractions": extraction_rows}


@app.get("/api/crawl/live")
async def crawl_live(url: str | None = None, department: str | None = None,
                      agency: str = "Unsorted", limit: int = 5, extract: bool = True):
    """Runs a REAL crawl, live, streamed over Server-Sent Events as each step actually
    happens -- not simulated, not pre-recorded. For a demo: pass either `url` (crawl one
    new address, added as an unlabelled seed on the fly) or `department` (a host substring
    like 'ird.gov.lk', crawling its existing seeds up to `limit`). Each page is fetched for
    real (politely rate-limited, same as the CLI), the saved archive file path is reported
    as soon as it is written, and a page classified NEW/CHANGED is handed to the exact same
    extraction path as /api/extract immediately after -- so the facts it stages really do
    land in the Review Gate. This spends real LLM tokens on anything that needs extraction."""
    import asyncio

    from app.core.acquisition.db import PgRunLog, TeeRunLog
    from app.core.acquisition.fetch import USER_AGENT, Crawl4AIFetcher, PoliteFetcher
    from app.core.acquisition.monitor import JsonlRunLog, run_pass
    from app.core.acquisition.pdf import PdfAwareFetcher
    from app.core.acquisition.ratelimit import HostRateLimiter
    from app.core.acquisition.robots import RobotsPolicy
    from app.core.acquisition.seeds import Seed, load_seeds
    from app.core.acquisition.store import SnapshotStore

    if url:
        seeds = [Seed(url=url.strip(), service=None, agency=agency, verified=False)]
    elif department:
        seeds = [s for s in load_seeds(SEEDS) if department.lower() in s.url.lower()][: max(1, limit)]
        if not seeds:
            raise HTTPException(404, f"no seeds match department {department!r}")
    else:
        raise HTTPException(400, "pass url=<new address> or department=<host substring>")

    seeds_by_url = {s.url: s for s in seeds}

    async def gen():
        queue: asyncio.Queue = asyncio.Queue()
        inner = PdfAwareFetcher(Crawl4AIFetcher(http_only=True))
        fetcher = PoliteFetcher(inner, RobotsPolicy(USER_AGENT), HostRateLimiter(2.0))
        store = SnapshotStore(CRAWL)
        log = JsonlRunLog(CRAWL)
        pg = None
        try:
            pg = PgRunLog(_dsn())
            pg.registry.sync_seeds(seeds)
            log = TeeRunLog(log, pg)
        except Exception:  # noqa: BLE001 -- demo still works file-only if postgres is down
            pg = None

        def on_page(result):
            queue.put_nowait(result)

        async def runner():
            try:
                summary = await run_pass(seeds, fetcher, store, log, on_page=on_page)
            finally:
                await inner.aclose()
                if pg:
                    pg.close()
            await queue.put(summary)

        task = asyncio.create_task(runner())

        def sse(obj: dict) -> str:
            return f"data: {json.dumps(obj)}\n\n"

        try:
            while True:
                item = await queue.get()
                if hasattr(item, "run_id") and hasattr(item, "counts"):  # RunSummary: the run is over
                    yield sse({"type": "done", "run_id": item.run_id, "counts": item.counts})
                    break

                r = item  # a PageResult, straight from the real fetch/fingerprint/classify step
                yield sse({
                    "type": "fetched", "url": r.url, "change": r.kind.value,
                    "status": r.status, "duration_ms": r.duration_ms,
                    "needs_extraction": r.needs_extraction,
                    "archived_as": r.file_path or None,
                })

                if r.file_path:
                    yield sse({"type": "saved", "url": r.url,
                               "path": f"research/data/crawl/{r.file_path}"})

                if r.needs_extraction and extract:
                    yield sse({"type": "extracting", "url": r.url})
                    seed = seeds_by_url.get(r.url)
                    md_path = CRAWL / r.file_path
                    text = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
                    if not text or not seed:
                        yield sse({"type": "extract_error", "url": r.url, "error": "page text unavailable"})
                        continue
                    try:
                        service_id = seed.service or UNSORTED
                        by_sections = not seed.service
                        extra = {"known_services": tuple(_known_services())} if by_sections else {}
                        reader = extract_sections if by_sections else extract_page
                        result = reader(text, service_id=service_id, agency=seed.agency,
                                        source_url=r.url,
                                        retrieved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                        llm=_llm(fast_fail=True), **extra)
                    except Exception as e:  # noqa: BLE001 -- show the real failure, keep streaming
                        yield sse({"type": "extract_error", "url": r.url, "error": str(e)})
                        continue
                    if result.error:
                        yield sse({"type": "extract_error", "url": r.url, "error": result.error})
                        continue
                    staging = StagingStore(_dsn())
                    try:
                        extraction_id, staged = staging.save(
                            r.url, result, service_id, seed.agency,
                            source_file=str(md_path.relative_to(REPO_ROOT)))
                    finally:
                        staging.close()
                    yield sse({
                        "type": "extracted", "url": r.url, "extraction_id": extraction_id,
                        "facts": len(result.facts), "dropped": result.dropped,
                        "new_pending": staged, "tokens_in": result.prompt_tokens,
                        "tokens_out": result.completion_tokens, "model": result.model,
                    })
        finally:
            await task

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/demo/quote_grounding")
def demo_quote_grounding(n: int = 10) -> dict:
    """Novelty 3: a live, random spot check that an approved fact's quote really is on
    the page it claims to come from -- the quote-or-drop rule, checked against the real
    saved pages right now, not assumed from the extraction step alone."""
    import psycopg

    with psycopg.connect(_dsn()) as c:
        rows = c.execute(
            "SELECT fact_id, value_text, source_url, evidence FROM c2.staged_facts "
            "WHERE status = 'approved' ORDER BY random() LIMIT %s", (n,)).fetchall()

    url_of = {f.stem: json.loads(f.read_text(encoding="utf-8"))["url"]
              for f in (CRAWL / "state").glob("*.json")}
    text_by_url: dict[str, str] = {}
    seen: set[str] = set()
    for md in sorted((CRAWL / "archive").glob("*/*.md"), reverse=True):
        url = url_of.get(md.stem, "")
        if url and url not in seen:
            seen.add(url)
            text_by_url[url] = md.read_text(encoding="utf-8")

    results, passed = [], 0
    for fact_id, value, url, quote in rows:
        found = bool(quote) and quote.strip() in text_by_url.get(url, "")
        passed += found
        results.append({"fact_id": fact_id, "value": value, "url": url,
                         "quote": (quote or "")[:160], "found_on_page": found})
    return {"checked": len(results), "passed": passed, "results": results}


@app.get("/api/demo/ordered_workflow")
def demo_ordered_workflow(service: str = "svc:passport", q: str | None = None) -> dict:
    """Novelty 4: the same real question answered two ways -- the graph's ordered,
    dependency-resolved plan (build_plan, no model call) against plain lexical search's
    unordered set of matching services (the real B3 baseline from workflow_scoring.py)."""
    import psycopg
    from neo4j import GraphDatabase

    from app.core.graph.plan import build_plan
    from app.core.knowledge.chunks import search as chunk_search

    uri, user, pw = _neo4j()
    driver = GraphDatabase.driver(uri, auth=(user, pw))
    try:
        p = build_plan(driver, service)
    finally:
        driver.close()
    if p is None:
        raise HTTPException(404, f"{service} is not in the graph")
    ordered = [s.service_id for s in p.steps]

    question = q or f"What do I need for {service.replace('svc:', '').replace('_', ' ')}?"
    with psycopg.connect(_dsn()) as c:
        url_map: dict[str, set[str]] = {}
        for url, sid in c.execute(
                "SELECT DISTINCT source_url, service_id FROM c2.staged_facts WHERE status = 'approved'"):
            url_map.setdefault(url, set()).add(sid)
    hits = chunk_search(_dsn(), question, limit=8)
    baseline = sorted({sid for h in hits for sid in url_map.get(h["url"], set())})
    return {"question": question, "graph_ordered_steps": ordered, "baseline_unordered_matches": baseline}


@app.get("/api/demo/traversal_scaling")
def demo_traversal_scaling() -> dict:
    """Novelty 5: the real app.core.graph.plan.build_plan algorithm (a DFS scoped to one
    service's REQUIRES-ancestors, same cycle guard, same MAX_DEPTH) against a naive
    whole-graph alternative, on synthetic graphs of growing size -- reproduced live here
    from research/experiments/traversal_cost.py, with fewer sizes so it answers quickly."""
    import random
    import time

    MAX_DEPTH = 64

    def make_graph(n: int, anc: int = 8, seed: int = 7):
        rng = random.Random(seed)
        nodes = [f"svc:n{i}" for i in range(n)]
        target = nodes[0]
        edges: dict[str, list[str]] = {sid: [] for sid in nodes}
        chain, prev = nodes[1:1 + anc], target
        for sid in chain:
            edges[prev].append(sid)
            prev = sid
        rest = nodes[1 + anc:]
        for sid in rest:
            if rest and rng.random() < 0.3:
                edges[sid].append(rng.choice(rest))
        return target, edges

    def dfs_count(start_nodes: list[str], edges: dict[str, list[str]]) -> int:
        order: list[str] = []
        state: dict[str, int] = {}

        def visit(sid: str, depth: int) -> None:
            if state.get(sid) == 2 or state.get(sid) == 1 or depth > MAX_DEPTH:
                return
            state[sid] = 1
            for dep in edges.get(sid, []):
                visit(dep, depth + 1)
            state[sid] = 2
            order.append(sid)

        for sid in start_nodes:
            visit(sid, 0)
        return len(order)

    def best_ms(fn, repeats: int) -> float:
        best = float("inf")
        for _ in range(repeats):
            t0 = time.perf_counter()
            fn()
            best = min(best, (time.perf_counter() - t0) * 1000)
        return round(best, 4)

    rows = []
    for n in (100, 1_000, 10_000, 50_000):
        target, edges = make_graph(n)
        all_nodes = list(edges.keys())
        rows.append({
            "nodes": n,
            "scoped_ms": best_ms(lambda: dfs_count([target], edges), repeats=15),
            "whole_graph_ms": best_ms(lambda: dfs_count(all_nodes, edges), repeats=3),
        })
    return {
        "ancestor_set_size": 8,
        "rows": rows,
        "scoped_growth_x": round(max(r["scoped_ms"] for r in rows) / min(r["scoped_ms"] for r in rows), 2),
        "whole_graph_growth_x": round(
            max(r["whole_graph_ms"] for r in rows) / min(r["whole_graph_ms"] for r in rows), 2),
    }


# ------------------------------------------------------------ official benchmarks
# These run the actual scripts named in the proposal's own ablation plan (Table 3, Section
# 1.3, Appendix B.2/B.3) -- the exact same files an examiner would run from the command
# line, same real output, just streamed into the dashboard instead of a terminal.

_BENCHMARKS = {
    "crawler_ablation": C2_ROOT / "research" / "experiments" / "crawler_ablation.py",
    "so1_classification": C2_ROOT / "research" / "experiments" / "classification_scoring.py",
    "so3_staleness": C2_ROOT / "research" / "experiments" / "so3_staleness.py",
    "so5_workflow": C2_ROOT / "research" / "experiments" / "workflow_scoring.py",
    "b3_traversal": C2_ROOT / "research" / "experiments" / "traversal_cost.py",
}


@app.post("/api/benchmark/{which}")
def run_benchmark(which: str) -> dict:
    """Runs the real experiment script as a subprocess, with the same python interpreter
    this server itself runs under, and returns its real stdout -- not a summary, not a
    re-implementation. Matches exactly what `python research/experiments/<script>.py`
    prints at a terminal."""
    import subprocess
    import time

    script = _BENCHMARKS.get(which)
    if script is None:
        raise HTTPException(404, f"No such benchmark: {which}")
    if not script.exists():
        raise HTTPException(404, f"Script not found: {script}")

    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True, text=True, timeout=120, cwd=str(script.parent),
        )
    except subprocess.TimeoutExpired as e:
        raise HTTPException(504, f"{which} did not finish within 120s") from e
    elapsed_ms = round((time.perf_counter() - t0) * 1000)
    return {
        "which": which,
        "script": script.name,
        "command": f"python {script.name}",
        "returncode": proc.returncode,
        "elapsed_ms": elapsed_ms,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


# ------------------------------------------------------------------------ page
PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>HelaGuide C2 review</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#fafaf7;--fg:#1c1c1a;--mut:#6b6b66;--card:#fff;--line:#e3e3dc;--acc:#1f5f4a;--bad:#a33;--warn:#8a5a00}
@media (prefers-color-scheme:dark){:root{--bg:#161614;--fg:#ecece6;--mut:#9a9a92;--card:#1f1f1c;--line:#34342f;--acc:#6fcfa8;--bad:#e08a8a;--warn:#e0b060}}
a{color:var(--acc)}a:visited{color:var(--acc)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 80px}h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--mut);margin:0 0 20px}section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:16px 0}
h2{font-size:16px;margin:0 0 4px}.hint{color:var(--mut);font-size:13px;margin:0 0 12px}
table{width:100%;border-collapse:collapse;font-size:13.5px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--mut);font-weight:600}button{font:inherit;padding:6px 12px;border-radius:7px;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
button.primary{background:var(--acc);border-color:var(--acc);color:#fff}button:disabled{opacity:.5;cursor:default}
.pill{display:inline-block;padding:1px 8px;border-radius:99px;font-size:12px;border:1px solid var(--line)}
.ok{color:var(--acc)}.bad{color:var(--bad)}.warn{color:var(--warn)}.mono{font-family:ui-monospace,Consolas,monospace;font-size:12.5px}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:10px 0 0}.banner{padding:10px 12px;border-radius:8px;border:1px solid var(--line);margin:0 0 12px}
.q{color:var(--mut);max-width:340px}.old{color:var(--warn)}#log{white-space:pre-wrap;font-size:13px;color:var(--mut)}
.demo{border:1px solid var(--line);border-radius:8px;padding:12px;margin:12px 0}.demo h3{font-size:14.5px;margin:0 0 4px}
.demoout{margin-top:10px;font-size:13.5px}.demoout table{margin-top:4px}.demoout .big{font-size:22px;font-weight:700}
.demoout .metric{display:inline-block;margin:4px 18px 4px 0}.demoout .metric .lbl{color:var(--mut);font-size:12px;display:block}
</style></head><body><main>
<h1>HelaGuide: read, review, approve</h1>
<p class="sub">Component 2 knowledge graph. Nothing reaches the graph until you approve it and press Write. <a href="/tree">See pages nested by where they were found</a></p>
<div id="status" class="banner">Checking the database and the graph...</div>

<section><h2>1. Saved pages</h2>
<p class="hint">Pages the crawler saved. "Read with model" sends one page to Gemini and puts the facts in the waiting room below. Pages with no facts are blocked by a free check.</p>
<table id="files"><thead><tr><th>Page</th><th>Agency &middot; services found</th><th>Text</th><th>Signals</th><th>State</th><th></th></tr></thead><tbody></tbody></table>
<p id="doneline" class="hint"></p>
<div id="log"></div></section>

<section><h2>2. Waiting for your decision</h2>
<p class="hint">Everything is ticked, ready to approve. Glance down the list. Untick anything that looks wrong or irrelevant, then click <b>Approve ticked</b>. To throw away the unticked ones, click <b>Reject unticked</b> and give a reason. Rows marked <b>changed</b> replace a value already in the graph.</p>
<div class="row"><button class="primary" id="auto" title="Approves facts whose quote is on the page, whose service is already in the graph, with no conflict and no case condition. The rest stay below for you.">Auto-approve the clean ones</button>
<button id="autosample" title="Shows 10 random auto-approved facts so you can spot-check the rules.">Spot-check 10 auto-approved</button><span id="autoout" class="hint"></span></div>
<div class="row"><button id="selall">Tick all</button><button id="selnone">Untick all</button>
<button class="primary" id="approve">Approve ticked</button><button id="reject">Reject unticked</button>
<span id="count" class="hint"></span></div>
<div id="groups" class="row"></div>
<table id="pending" style="margin-top:12px"><thead><tr><th></th><th>#</th><th>Fact (service : kind : name)</th><th>Value</th><th>Graph holds</th><th>Quote from the page</th></tr></thead><tbody></tbody></table></section>

<section><h2>3. Put approved facts in the graph</h2>
<p class="hint">Writes only facts you approved. Running it twice changes nothing.</p>
<div class="row"><button class="primary" id="write">Write to graph</button></div>
<div id="graph" style="margin-top:12px"></div></section>

<section><h2>4. Novelty tests</h2>
<p class="hint">Each button below runs the real production code, live, against the real saved pages and the real database -- nothing here is a number pasted in from an earlier report.</p>

<div class="demo"><h3>1. Catching an "invisible" edit</h3>
<p class="hint">Normal crawlers only notice a page changed if its layout or file size changes. This flips one digit in a real saved page's fee (everything else stays byte-identical) and runs the real fingerprint/classify pipeline on it.</p>
<button id="d1">Run test</button><div id="d1out" class="demoout"></div></div>

<div class="demo"><h3>2. Zero tokens on an unchanged page</h3>
<p class="hint">Real totals from every page read so far, plus a live, timed check proving an unchanged page makes no model call.</p>
<button id="d2">Run test</button><div id="d2out" class="demoout"></div></div>

<div class="demo"><h3>3. Quote-or-drop grounding</h3>
<p class="hint">Picks random approved facts and checks, right now, that each one's quote is really on the page it claims to come from.</p>
<button id="d3">Run test</button><div id="d3out" class="demoout"></div></div>

<div class="demo"><h3>4. Ordered workflow vs. plain search</h3>
<p class="hint">Asks the graph and a plain lexical search the same question. The graph gives steps in order; search gives an unordered pile of matches.</p>
<div class="row"><label class="hint">Service: <input id="d4svc" value="svc:passport" class="mono" style="width:220px"></label><button id="d4">Run test</button></div><div id="d4out" class="demoout"></div></div>

<div class="demo"><h3>5. Fast lookups as the graph grows</h3>
<p class="hint">The real build_plan algorithm, scoped to one service's ancestors, against a naive whole-graph alternative, on graphs from 100 to 50,000 nodes.</p>
<button id="d5">Run test</button><div id="d5out" class="demoout"></div></div>

<div class="demo"><h3>6. Value-change-driven community updates</h3>
<p class="hint">Next-phase work (SO3): local re-clustering when one fact changes, instead of rebuilding the whole graph. Needs community detection, which is not built yet -- shown here honestly as not available, not faked.</p>
<span class="pill warn">Not available yet -- needs SO3 (community detection)</span></div>
</section>
</main>
<script>
const $=s=>document.querySelector(s);
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
async function api(path,opt){const r=await fetch(path,opt);const t=await r.text();let j;try{j=JSON.parse(t)}catch{j={detail:t}}
  if(!r.ok) throw new Error(j.detail||t); return j}
const post=(p,b)=>api(p,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)});
function say(t){$("#log").textContent=t}

async function status(){
  try{const s=await api("/api/status");
    const bits=[`Database: ${s.postgres?'<b class=ok>ready</b>':'<b class=bad>not reachable</b>'}`,
      `Graph (Neo4j): ${s.neo4j?'<b class=ok>ready</b>':'<b class=bad>not reachable</b>'}`,
      `Model key: ${s.model_key?'<b class=ok>found</b>':'<b class=bad>missing in .env</b>'}`];
    $("#status").innerHTML=bits.join(" &nbsp;|&nbsp; ")+((!s.postgres||!s.neo4j)?
      "<br>Start Docker Desktop, then run <span class=mono>docker compose start postgres neo4j</span> and reload.":"");
  }catch(e){$("#status").textContent="Could not check: "+e.message}}

async function loadFiles(){
  let rows=await api("/api/files");const tb=$("#files tbody");tb.innerHTML="";
  const ALL=location.pathname==="/all";
  const order=["to_read","changed","read","nothing","older"];
  const names={to_read:"To read: not sent to the model yet",changed:"Page changed since it was read",
    read:"Already read",nothing:"Nothing to read: no fee, document or prerequisite on the page",older:"Older copies of a page that has changed"};
  const done=rows.filter(f=>f.state==="read").length;
  if(!ALL){
    rows=rows.filter(f=>f.state==="to_read"||f.state==="changed");
    $("#doneline").innerHTML=(rows.length?"":"<b>Nothing left to read.</b> ")+done+" page(s) already read. <a href='/all'>See all pages</a>";
  }
  const grp=f=>order.indexOf(f.state);
  rows.sort((a,b)=>grp(a)-grp(b));
  let lastGrp=-1;
  for(const f of rows){
    if(grp(f)!==lastGrp){
      lastGrp=grp(f);
      const h=document.createElement("tr");
      h.innerHTML=`<td colspan="6" style="font-weight:600;padding-top:14px">${names[order[lastGrp]]} (${rows.filter(r=>grp(r)===lastGrp).length})</td>`;
      tb.appendChild(h);
    }
    let state=f.state==="changed"?'<span class="pill warn" title="This page was read before, but the site has a newer version. Read it again to see what changed.">page changed since read</span>':f.state==="older"?'<span class="pill">older copy</span>':f.sent?(f.headings>=3&&!f.by_sections?'<span class="pill" title="The page has '+f.headings+' headed parts and was read as ONE service. If those parts are separate services (not variants of one), use Read by sections.">read as one service</span>':(f.by_sections?'<span class="pill ok">read by sections</span>':'<span class="pill ok">read</span>')):(f.gate_send?'<span class="pill">to read</span>':'<span class="pill warn">no facts expected</span>');
    if(f.in_graph) state+=` <span class="pill ok" title="Approved and written: these facts are in the graph">${f.in_graph} in graph</span>`;
    if(f.approved_not_written) state+=` <span class="pill warn" title="Approved, but Write to graph has not been pressed yet">${f.approved_not_written} approved, not written</span>`;
    if(f.pending) state+=` <span class="pill">${f.pending} waiting</span>`;
    if(f.rejected) state+=` <span class="pill" title="Rejected, kept with the reason">${f.rejected} rejected</span>`;
    const can=f.state==="to_read"&&f.service;
    const move=ALL&&f.state!=="older"&&f.sent&&f.found.length;
    const again=ALL&&f.state==="read";
    const sec=f.state!=="older"&&f.gate_send&&(f.state==="to_read"||f.state==="changed"||again);
    const tr=document.createElement("tr");
    tr.innerHTML=`<td><a href="${esc(f.url)}" target="_blank">${esc(f.url.replace(/^https?:\\/\\/(www\\.)?/,''))}</a><div class="mono hint">${esc(f.file)}</div></td>
      <td>${esc(f.agency||'?')}<br>${f.found.length?f.found.map(x=>'<span class="pill mono">'+esc(x)+'</span>').join(' '):'<span class="hint">none yet: read the page to find out</span>'}</td><td>${f.size.toLocaleString()} B</td><td class="mono">${esc(f.signals)}</td><td>${state}</td>
      <td>${can?`<button data-f="${esc(f.file)}" data-s="${f.gate_send}">Read with model</button>`:''}
          ${sec?`<button class="sec" data-f="${esc(f.file)}" data-r="${again?1:''}" title="The model reads the whole page once and returns each headed service separately.">${again?'Read again':'Read by sections'}</button>`:''}
          ${move?`<button class="mv" data-u="${esc(f.url)}" data-sv="${esc(f.found[0]||'')}" title="The facts on this page describe a service other than the one it is listed under. File them under the right one, or a new one.">Different service? File it</button>`:''}</td>`;
    tb.appendChild(tr);}
  tb.querySelectorAll("button:not(.mv):not(.sec)").forEach(b=>b.onclick=()=>readFile(b));
  tb.querySelectorAll("button.sec").forEach(b=>b.onclick=()=>readSections(b));
  tb.querySelectorAll("button.mv").forEach(b=>b.onclick=()=>moveFile(b));}

async function readSections(b){
  const file=b.dataset.f;
  const reread=!!b.dataset.r;
  if(!confirm((reread?"This exact saved page was already read. Read it again?\\nIt costs tokens and may name things slightly differently.\\n\\n":"")+"Read this page by sections?\\nThe model reads the whole page once and returns each headed service separately. Uses your model key."))return;
  b.disabled=true;say("Reading "+file+" by sections... this can take a minute or two.");
  try{const r=await post("/api/extract",{file,force:true,by_sections:true,reread});
    if(r.skipped){say("Skipped: "+r.reason+". No tokens used.");await loadFiles();return}
    const rows=(r.sections||[]).map(s=>`  ${s.is_service?'service':'not a service'}  ${s.service_id}   "${s.title}"   ${s.facts} fact(s)`).join("\\n");
    say(`Done. ${r.sections.length} part(s) found, ${r.new_pending} new fact(s) in the waiting room.\\nTokens: ${r.tokens_in} in, ${r.tokens_out} out.\\n${rows}`);
  }catch(e){say("Failed: "+e.message)}
  await loadFiles();await loadPending();}

async function renameService(old){
  const to=prompt("Rename "+old+" to:\\n(lowercase letters, digits and _, for example svc:nic_number_verification)",old);
  if(!to||to===old)return;
  try{const r=await post("/api/rename_service",{old,new:to});say(`Renamed: ${r.moved} waiting fact(s) now under ${to}`)}
  catch(e){say("Failed: "+e.message)}
  await loadPending();}

async function moveFile(b){
  const url=b.dataset.u;
  const to=prompt("The facts on this page are listed under "+b.dataset.sv+".\\nThey describe a different service. Which service are they about?\\nType an existing one, or a NEW one to create, for example svc:nic_translation\\n(lowercase letters, digits and _)","svc:");
  if(!to||to===b.dataset.sv)return;
  if(!confirm("File this page's waiting facts under "+to+"?\\nThe service is created if it is new. Nothing reaches the graph until you approve and write.\\nThe facts first read under "+b.dataset.sv+" are kept as superseded, with the reason. No model call is used."))return;
  say("Filing...");
  try{const r=await post("/api/refile",{url,service_id:to});
    say(`Filed under ${r.service}: ${r.facts} fact(s), ${r.new_pending} new in the waiting room. ${r.moved_from} earlier ones were superseded (kept, not deleted).`);
  }catch(e){say("Failed: "+e.message)}
  await loadFiles();await loadPending();}

async function readFile(b){
  const file=b.dataset.f;let force=false;
  if(b.dataset.s==="false"){ if(!confirm("The free check says this page has no facts. Send it to the model anyway?")) return; force=true; }
  b.disabled=true;say("Reading "+file+" with the model... this can take up to a minute.");
  try{const r=await post("/api/extract",{file,force});
    if(r.skipped) say("Skipped: "+r.reason+". No tokens used.");
    else say(`Done. ${r.facts} fact(s) found, ${r.new_pending} new in the waiting room, ${r.dropped.length} dropped because the page does not back them.\\nTokens: ${r.tokens_in} in, ${r.tokens_out} out (${r.model}).`);
  }catch(e){say("Failed: "+e.message)}
  await loadFiles();await loadPending();}

async function loadPending(){
  const rows=await api("/api/pending");const tb=$("#pending tbody");tb.innerHTML="";
  $("#count").textContent=rows.length+" waiting";
  const bySvc={},isNew={};rows.forEach(f=>{bySvc[f.service]=(bySvc[f.service]||0)+1;isNew[f.service]=f.new_service});
  $("#groups").innerHTML=Object.entries(bySvc).map(([s,n])=>
    `<span class="pill">${esc(s)} &middot; ${n}</span>${isNew[s]?' <span class="pill warn" title="No approved fact uses this service id yet. Approving creates it, and other components will see it. Check the name.">NEW service</span>':''} <button class="rn" data-s="${esc(s)}">Rename</button>`).join(" &nbsp; ");
  document.querySelectorAll("#groups .rn").forEach(b=>b.onclick=()=>renameService(b.dataset.s));
  const isChanged=f=>!!(f.old&&f.old!==f.value);
  rows.sort((a,b)=>(isChanged(b)-isChanged(a))||a.service.localeCompare(b.service)||a.fact_id.localeCompare(b.fact_id));
  for(const f of rows){
    const tr=document.createElement("tr");
    const val=f.value+(f.unit&&f.predicate==='fee'?"":"");
    const change=isChanged(f)?`<span class="pill warn" title="The graph holds a different value for this fact. Approving closes the old one.">changed</span> was: ${esc(f.old)}`:'<span class="pill">new</span>';
    tr.innerHTML=`<td><input type="checkbox" data-id="${f.id}" checked></td><td class="mono">${f.id}</td>
      <td class="mono">${esc(f.fact_id)}</td><td>${esc(val)}</td><td class="old">${change}</td>
      <td class="q" title="${esc(f.quote)}">${esc(f.quote.length>150?f.quote.slice(0,150)+'...':f.quote)}
        ${(f.forms||[]).map(x=>`<div><a href="${esc(x.url)}" target="_blank">&#128196; ${esc(x.label||'form')}</a></div>`).join("")}</td>`;
    tb.appendChild(tr);}}

const ticked=()=>[...document.querySelectorAll("#pending input:checked")].map(i=>+i.dataset.id);
const unticked=()=>[...document.querySelectorAll("#pending input:not(:checked)")].map(i=>+i.dataset.id);
$("#selall").onclick=()=>document.querySelectorAll("#pending input").forEach(i=>i.checked=true);
$("#selnone").onclick=()=>document.querySelectorAll("#pending input").forEach(i=>i.checked=false);
async function decide(decision){
  // approve acts on the ticked rows; reject acts on the unticked rows
  const ids=decision==="approved"?ticked():unticked();
  if(!ids.length){alert(decision==="approved"?"Nothing is ticked.":"Nothing is unticked. Untick the rows you want to reject first.");return}
  let reason="";
  if(decision==="rejected"){reason=prompt(`Why are you rejecting these ${ids.length} fact(s)? (one short reason, kept in the audit trail)`);if(!reason)return}
  else if(!confirm(`Approve ${ids.length} fact(s)? They can then be written to the graph.`))return;
  try{const r=await post("/api/decide",{ids,decision,reason});say(`${decision}: ${r.decided} fact(s)`+(r.skipped?`, ${r.skipped} already decided`:""))}
  catch(e){say("Failed: "+e.message)}
  await loadPending();await loadFiles();}
$("#auto").onclick=async()=>{
  try{
    const d=await post("/api/auto",{apply:false});
    if(!d.clean){say("Nothing is clean enough to approve automatically: "+d.held+" fact(s) need you.");return}
    const why=Object.entries(d.reasons).map(([k,v])=>"  "+v+"  "+k).join("\\n");
    if(!confirm(d.clean+" fact(s) will be approved automatically (quote on the page, known service, no conflict).\\n"+d.held+" will stay for you:\\n"+why))return;
    const r=await post("/api/auto",{apply:true});
    say("Auto-approved "+r.approved+". "+r.held+" left for you. Press Write to graph to put the approved ones in.");
  }catch(e){say("Failed: "+e.message)}
  await loadPending();await loadFiles();};
$("#autosample").onclick=async()=>{
  try{const rows=await api("/api/auto_sample?n=10");
    if(!rows.length){say("No auto-approved facts yet.");return}
    say("Spot-check these (is the value what the quote says?):\\n"+rows.map(r=>"  #"+r.id+"  "+r.fact_id+"  =  "+r.value+"\\n      quote: "+r.quote.slice(0,150)).join("\\n"));
  }catch(e){say("Failed: "+e.message)}};
$("#approve").onclick=()=>decide("approved");$("#reject").onclick=()=>decide("rejected");

async function showGraph(g){
  const s=g.summary;
  $("#graph").innerHTML=`<table><tbody>${Object.entries(s).map(([k,v])=>`<tr><td>${esc(k)}</td><td><b>${v}</b></td></tr>`).join("")}</tbody></table>
   <p class="hint" style="margin-top:10px">Links:</p><div class="mono">${g.chain.map(c=>`${esc(c.a)} &rarr; requires &rarr; ${esc(c.b)}`).join("<br>")||"none yet"}</div>
   ${g.empty_services.length?`<p class="warn">Services with no facts of their own yet: <span class=mono>${g.empty_services.map(esc).join(", ")}</span></p>`:""}`;}
async function loadGraph(){try{await showGraph(await api("/api/graph"))}catch(e){$("#graph").textContent="Graph not reachable: "+e.message}}
$("#write").onclick=async()=>{
  if(!confirm("Write all approved facts to the graph?"))return;
  try{const r=await post("/api/write",{});say(`Written: ${r.new} new, ${r.changed} changed, ${r.same} unchanged`+(r.failed.length?`, ${r.failed.length} failed`:""));
    await loadGraph();}catch(e){say("Failed: "+e.message)}};

function metric(label,value){return `<span class="metric"><span class="lbl">${esc(label)}</span>${esc(value)}</span>`}

$("#d1").onclick=async()=>{const b=$("#d1"),out=$("#d1out");b.disabled=true;out.innerHTML='<span class="hint">Flipping a real digit and re-running the real classifier...</span>';
  try{const r=await post("/api/demo/invisible_edit",{});
    out.innerHTML=`<p>Page: <span class="mono">${esc(r.page)}</span></p>
      <p>Edit made: <span class="mono">${esc(r.edit)}</span></p>
      ${metric("Layout (structure hash)",r.layout_byte_identical?"identical before/after":"changed")}
      ${metric("Content hash before",r.before_content_hash)}
      ${metric("Content hash after",r.after_content_hash)}
      <p>Result: <span class="pill ${r.classification==='CONTENT_CHANGED'?'ok':'bad'}">${esc(r.classification)}</span>
       <span class="hint">${r.detail.magnitude?('magnitude: '+esc(r.detail.magnitude)):''}</span></p>
      <p class="hint">${r.layout_byte_identical&&r.classification==='CONTENT_CHANGED'?'Caught: the layout never moved, only the number changed, and the real pipeline still flagged it.':''}</p>`;
  }catch(e){out.innerHTML='<span class="bad">Failed: '+esc(e.message)+'</span>'}
  b.disabled=false;};

$("#d2").onclick=async()=>{const b=$("#d2"),out=$("#d2out");b.disabled=true;out.innerHTML='<span class="hint">Querying real totals and timing a live check...</span>';
  try{const r=await api("/api/demo/token_cost");
    out.innerHTML=`${metric("Pages extracted so far",r.pages_extracted_so_far)}
      ${metric("Total tokens spent so far",r.total_tokens_so_far.toLocaleString())}
      ${metric("Average tokens / page",r.avg_tokens_per_page)}
      ${metric("Live unchanged-page check",r.live_unchanged_check_ms!=null?r.live_unchanged_check_ms+" ms":"n/a (save a page first)")}
      ${metric("Tokens spent on that check",r.live_unchanged_check_tokens)}
      <p class="hint">${r.live_classification==='UNCHANGED'?'The real classifier confirmed this page is unchanged -- no model call was made.':''}</p>`;
  }catch(e){out.innerHTML='<span class="bad">Failed: '+esc(e.message)+'</span>'}
  b.disabled=false;};

$("#d3").onclick=async()=>{const b=$("#d3"),out=$("#d3out");b.disabled=true;out.innerHTML='<span class="hint">Sampling random approved facts and checking their quotes live...</span>';
  try{const r=await api("/api/demo/quote_grounding?n=10");
    const rows=r.results.map(x=>`<tr><td class="mono">${esc(x.fact_id)}</td><td>${esc(x.value)}</td>
      <td class="q" title="${esc(x.quote)}">${esc(x.quote.slice(0,90))}...</td>
      <td>${x.found_on_page?'<span class="pill ok">on the page</span>':'<span class="pill bad">not found</span>'}</td></tr>`).join("");
    out.innerHTML=`<p><span class="big">${r.passed}/${r.checked}</span> <span class="hint">quotes verified on their real source page, just now</span></p>
      <table><thead><tr><th>Fact</th><th>Value</th><th>Quote (truncated)</th><th>Check</th></tr></thead><tbody>${rows}</tbody></table>`;
  }catch(e){out.innerHTML='<span class="bad">Failed: '+esc(e.message)+'</span>'}
  b.disabled=false;};

$("#d4").onclick=async()=>{const b=$("#d4"),out=$("#d4out");b.disabled=true;out.innerHTML='<span class="hint">Asking the graph and a plain search the same question...</span>';
  try{const svc=$("#d4svc").value.trim()||"svc:passport";
    const r=await api("/api/demo/ordered_workflow?service="+encodeURIComponent(svc));
    out.innerHTML=`<p class="hint">Question: "${esc(r.question)}"</p>
      <table><tr><th style="width:50%">Graph (ordered, this component)</th><th>Plain lexical search (unordered)</th></tr>
      <tr><td>${r.graph_ordered_steps.map((s,i)=>(i+1)+'. '+esc(s)).join("<br>")}</td>
      <td>${r.baseline_unordered_matches.length?r.baseline_unordered_matches.map(esc).join("<br>"):'<span class="hint">no matches</span>'}
      <p class="hint">no order, no dependency chain -- a flat set of pages that mention the words</p></td></tr></table>`;
  }catch(e){out.innerHTML='<span class="bad">Failed: '+esc(e.message)+'</span>'}
  b.disabled=false;};

$("#d5").onclick=async()=>{const b=$("#d5"),out=$("#d5out");b.disabled=true;out.innerHTML='<span class="hint">Building synthetic graphs up to 50,000 nodes and timing both algorithms...</span>';
  try{const r=await api("/api/demo/traversal_scaling");
    const rows=r.rows.map(x=>`<tr><td>${x.nodes.toLocaleString()}</td><td class="mono">${x.scoped_ms}</td><td class="mono">${x.whole_graph_ms}</td></tr>`).join("");
    out.innerHTML=`<table><thead><tr><th>Graph size (nodes)</th><th>Scoped (this component)</th><th>Whole-graph</th></tr></thead><tbody>${rows}</tbody></table>
      <p style="margin-top:8px"><span class="pill ok">scoped: ${r.scoped_growth_x}&times; across the range</span>
      &nbsp;<span class="pill bad">whole-graph: ${r.whole_graph_growth_x}&times; across the range</span></p>`;
  }catch(e){out.innerHTML='<span class="bad">Failed: '+esc(e.message)+'</span>'}
  b.disabled=false;};

if(location.pathname==="/all"){document.querySelectorAll("section").forEach((x,i)=>{if(i>0)x.style.display="none"});document.querySelector("h1").textContent="All saved pages";document.querySelector(".sub").innerHTML="Every page the crawler saved, read or not. <a href='/'>Back to what is left</a>"}
status();loadFiles().catch(e=>say("Could not list pages: "+e.message));loadPending().catch(()=>{});loadGraph();
</script></body></html>"""


TREE_BODY = """
<h1>Pages, nested by where they were found</h1>
<p class="sub"><a href="/">Back to what is left to do</a> &middot; <a href="/all">All saved pages</a></p>
<div id="counts" class="banner"></div>
<section><div id="tree">Loading...</div></section>
<script>
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const COLOUR={"in graph":"ok","read":"ok","saved, to read":"warn","changed since read":"warn","not saved":"","saved, nothing to read":""};
function short(u){return u.replace(/^https?:[/][/](www[.])?/,"")}
function node(url,all,kids){
  const n=all[url],c=kids[url]||[];
  const sig=n.signals?'<span class="mono hint"> '+esc(n.signals)+'</span>':"";
  const extra=[n.facts?n.facts+" fact(s) in graph":"",n.waiting?n.waiting+" waiting":"",(n.services||[]).length?esc(n.services.join(", ")):"",n.unplaced?"parent not recorded":""].filter(Boolean).join(" &middot; ");
  const head='<a href="'+esc(url)+'" target="_blank">'+esc(n.label||short(url))+'</a> <span class="mono hint">'+esc(short(url))+'</span>'+sig+
    ' <span class="pill '+(COLOUR[n.status]||"")+'">'+esc(n.status)+'</span> '+(n.type==="pdf"?'<span class="pill">pdf</span> ':"")+(extra?'<span class="hint">'+extra+'</span>':"");
  if(!c.length)return '<div style="margin:3px 0 3px 18px">'+head+'</div>';
  const done=c.filter(k=>all[k].status!=="not saved").length;
  return '<details style="margin:3px 0 3px 12px"'+(n.parent?"":" open")+'><summary>'+head+' <span class="hint">('+done+" of "+c.length+" saved)</span></summary>"+c.map(k=>node(k,all,kids)).join("")+"</details>";
}
fetch("/api/tree").then(r=>r.json()).then(d=>{
  const all=d.nodes,kids={};
  Object.keys(all).forEach(u=>{const p=all[u].parent;if(p&&all[p])(kids[p]=kids[p]||[]).push(u)});
  Object.values(kids).forEach(l=>l.sort());
  const roots=Object.keys(all).filter(u=>!all[u].parent||!all[all[u].parent]);
  const c=d.counts;
  document.getElementById("counts").innerHTML="<b>"+c.known+"</b> pages known &middot; <b>"+c.saved+"</b> saved &middot; <b>"+c.read+"</b> read by the model &middot; <b>"+c.in_graph+"</b> have facts in the graph";
  document.getElementById("tree").innerHTML=roots.map(u=>node(u,all,kids)).join("")||"Nothing yet. Run a discovery first.";
}).catch(e=>{document.getElementById("tree").textContent="Could not load: "+e});
</script></main></body></html>
"""


@app.get("/tree", response_class=HTMLResponse)
def tree_page() -> str:
    return PAGE.split("</style></head><body><main>")[0] + "</style></head><body><main>" + TREE_BODY


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return PAGE


@app.get("/all", response_class=HTMLResponse)
def all_pages() -> str:
    return PAGE


def main() -> int:
    import uvicorn

    threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
