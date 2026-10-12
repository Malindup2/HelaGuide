"""Command line for stage 1.

    python -m app.core.acquisition --check-seeds
    python -m app.core.acquisition                       # one monitoring pass over the seeds
    python -m app.core.acquisition --db                  # same, and log to PostgreSQL (schema c2)
    python -m app.core.acquisition --report              # measured change profile
    python -m app.core.acquisition --discover URL        # list and score the pages URL links to

Run it from components/c2-knowledge-graph/service/ with the extras installed:
    pip install -e ".[dev,crawl,db]"
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import yaml

from app.core.acquisition import report as report_mod
from app.core.acquisition.discover import Candidate, discover
from app.core.acquisition.fetch import USER_AGENT, Crawl4AIFetcher, PoliteFetcher
from app.core.acquisition.monitor import JsonlRunLog, PageResult, run_pass
from app.core.acquisition.pdf import PdfAwareFetcher
from app.core.acquisition.ratelimit import HostRateLimiter
from app.core.acquisition.robots import RobotsPolicy
from app.core.acquisition.seeds import load_seeds, summarise
from app.core.acquisition.store import SnapshotStore

C2_ROOT = Path(__file__).resolve().parents[4]
REPO_ROOT = C2_ROOT.parents[1]
DEFAULT_SEEDS = C2_ROOT / "research" / "data" / "seed_urls.yaml"
DEFAULT_ROOT = C2_ROOT / "research" / "data" / "crawl"


def _print_page(r: PageResult) -> None:
    extra = ""
    if "simhash_distance" in r.detail:
        extra = f"   ({r.detail['simhash_distance']} bits, {r.detail['char_delta']:+d} chars)"
    if r.error:
        extra = f"   {r.error}"
    if r.detail.get("thin_content"):
        extra += "   [thin content: try browser mode]"
    print(f"  {r.kind.value:<18} {r.url}{extra}")


def _dsn(args: argparse.Namespace) -> str | None:
    """Explicit --database-url wins; --db reads the repo .env."""
    if args.database_url:
        return args.database_url
    if args.db:
        from app.core.acquisition.db import dsn_from_dotenv

        dsn = dsn_from_dotenv(REPO_ROOT / ".env")
        if dsn is None:
            raise SystemExit(f"--db needs POSTGRES_USER, POSTGRES_PASSWORD and POSTGRES_DB in {REPO_ROOT / '.env'}")
        return dsn
    return None


def _fetcher(args: argparse.Namespace):
    inner = PdfAwareFetcher(Crawl4AIFetcher(http_only=not args.browser))
    return inner, PoliteFetcher(inner, RobotsPolicy(USER_AGENT), HostRateLimiter(args.min_interval))


async def _run(args: argparse.Namespace) -> int:
    seeds = load_seeds(args.seeds)
    if not seeds:
        print(f"no seeds in {args.seeds}")
        return 1
    inner, fetcher = _fetcher(args)
    store, log = SnapshotStore(args.root), JsonlRunLog(args.root)
    pg = None
    if (dsn := _dsn(args)) is not None:
        from app.core.acquisition.db import PgRunLog, TeeRunLog

        pg = PgRunLog(dsn, mode="browser" if args.browser else "http")
        pg.registry.sync_seeds(seeds)
        log = TeeRunLog(log, pg)
    print(f"monitoring {len(seeds)} pages [{'browser' if args.browser else 'http-only'}"
          f"{', postgres' if pg else ''}]\n")
    try:
        summary = await run_pass(seeds, fetcher, store, log, on_page=_print_page)
    finally:
        await inner.aclose()
        if pg:
            pg.close()
    print(f"\nrun {summary.run_id}")
    for kind, n in sorted(summary.counts.items(), key=lambda kv: -kv[1]):
        print(f"  {kind:<18} {n}")
    print(f"\n{len(summary.to_extract)} page(s) need extraction")
    return 0


def _write_candidates(path: Path, start: str, found: list[Candidate]) -> None:
    rows = [{
        "url": c.url, "label": c.label, "signals": c.signals.flags, "score": c.signals.score,
        "chars": c.chars, "source_type": c.source_type, "discovered_from": c.discovered_from,
        **({"error": c.error} if c.error else {}),
        **({"duplicate_of": c.duplicate_of} if c.duplicate_of else {}),
    } for c in sorted(found, key=lambda c: -c.signals.score)]
    header = (
        "# Candidate pages found by --discover. Signals: F=fee D=documents P=prerequisite.\n"
        "# Nothing here is monitored. Open a page, and if it states a fee, a document list or a\n"
        "# prerequisite, copy it into seed_urls.yaml with its service and agency.\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    from app.core.acquisition import tree

    tree.merge(path.parent, start, rows)  # keep which page was found on which, across runs
    path.write_text(header + yaml.safe_dump({"start": start, "candidates": rows},
                                            sort_keys=False, allow_unicode=True), encoding="utf-8")


async def _discover(args: argparse.Namespace) -> int:
    known = {s.url for s in load_seeds(args.seeds)} if args.seeds.exists() else set()
    inner, fetcher = _fetcher(args)
    registry = None
    if (dsn := _dsn(args)) is not None:
        from app.core.acquisition.db import PageRegistry

        registry = PageRegistry(dsn)
    print(f"discovering from {args.discover} (depth {args.depth}, up to {args.limit})\n")
    try:
        from app.core.acquisition.exclusions import Exclusions

        rules = Exclusions.load(args.seeds.parent / "exclusions.yaml")
        found = await discover(args.discover, fetcher, depth=args.depth, limit=args.limit,
                               screen=not args.no_screen, known=known,
                               extra_skip=tuple(p for _, p in rules.link))
    except RuntimeError as e:
        print(e)
        return 1
    finally:
        await inner.aclose()

    for c in found:
        mark = c.signals.flags if c.ok else ("ERR" if not args.no_screen else "...")
        dup = f"  (same text as {c.duplicate_of})" if c.duplicate_of else ""
        print(f"  [{mark}] {c.source_type:<4} {c.chars:>6}ch  {c.url}  {c.label[:40]}{dup}")
        if registry:
            registry.record_candidate(c.url, c.discovered_from, c.source_type,
                                      has_fee=c.signals.has_fee, has_docs=c.signals.has_docs,
                                      has_prereq=c.signals.has_prereq, score=c.signals.score)
    if registry:
        registry.close()
    out = args.root / "candidate_seeds.yaml"
    _write_candidates(out, args.discover, found)
    scored = sum(1 for c in found if c.signals.score)
    print(f"\n{len(found)} candidate(s), {scored} with at least one signal -> {out}")
    return 0


def _extract(args: argparse.Namespace) -> int:
    """Stage 2 on one archived page: model reads the Markdown, facts come out as pending."""
    import os
    from datetime import datetime, timezone

    from app.core.acquisition.db import read_dotenv
    from app.core.acquisition.discover import strip_menus
    from app.core.extraction.extractor import MAX_PAGE_CHARS, SYSTEM, extract_page
    from app.core.extraction.llm import OpenAICompatClient

    if not (args.service and args.source_url):
        print("--extract-file needs --service svc:<slug> and --source-url URL")
        return 1
    text = args.extract_file.read_text(encoding="utf-8")
    body = strip_menus(text)

    if args.show_prompt:
        print(SYSTEM)
        print(f"page: {args.source_url}\nservice: {args.service}")
        print(f"page text: {len(text)} chars, {len(body)} after removing menus "
              f"(limit {MAX_PAGE_CHARS}); about {len(body) // 4} tokens in")
        return 0

    env = read_dotenv(REPO_ROOT / ".env")
    key = os.environ.get("LLM_API_KEY") or env.get("LLM_API_KEY", "")
    if not key:
        print("no LLM_API_KEY: set it in .env (or the environment). Use --show-prompt to "
              "check the input without a model.")
        return 1
    llm = OpenAICompatClient(key, args.model, args.llm_base_url,
                             reasoning_effort=args.reasoning_effort)
    result = extract_page(text, service_id=args.service, agency=args.agency or "",
                          source_url=args.source_url,
                          retrieved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                          llm=llm)
    if result.error:
        print(f"extraction failed: {result.error}")
        return 1
    print(f"model {result.model}: {result.prompt_tokens} tokens in, {result.completion_tokens} out"
          f"{'  [page truncated]' if result.truncated else ''}\n")
    for f in result.facts:
        unit = f" {f.unit}" if f.unit else ""
        num = f"  = {f.value_num:g}{unit}" if f.value_num is not None else ""
        print(f"  {f.fact_id:<46} {f.value_text[:50]}{num}")
    for d in result.dropped:
        print(f"  DROPPED {d['fact_id']} = {d.get('value', '')[:40]!r}: {d['reason']}")
        if d.get("evidence"):
            print(f"          quoted: {d['evidence'][:110]!r}")
    print(f"\n{len(result.facts)} fact(s), {len(result.dropped)} dropped")

    if args.dry_run:
        print("dry run: nothing saved")
        return 0
    dsn = _dsn(args)
    if dsn is None:
        print("not saved: add --db to stage these facts in PostgreSQL (or --dry-run)")
        return 0
    from app.core.extraction.staging import StagingStore

    store = StagingStore(dsn)
    try:
        try:
            saved_as = str(args.extract_file.resolve().relative_to(REPO_ROOT))
        except ValueError:
            saved_as = str(args.extract_file)
        extraction_id, staged = store.save(args.source_url, result, args.service, args.agency,
                                           source_file=saved_as)
    finally:
        store.close()
    print(f"saved: extraction {extraction_id}, {staged} new pending fact(s)")
    return 0


def _review(args: argparse.Namespace) -> int:
    """The review gate: list pending facts, approve or reject them, every decision audited."""
    dsn = _dsn(args)
    if dsn is None:
        print("review needs the database: add --db")
        return 1
    from app.core.graph.review import ReviewStore

    store = ReviewStore(dsn)
    try:
        if args.approve or args.reject:
            decision = "approved" if args.approve else "rejected"
            raw = args.approve or args.reject
            pending = store.pending(args.service, limit=10_000)
            if raw.strip().lower() == "all":
                ids = [f.staged_id for f in pending]
            else:
                ids = [int(x) for x in raw.split(",") if x.strip()]
            if decision == "rejected" and not args.reason:
                print("a rejection needs --reason, so the audit trail says why")
                return 1
            done, skipped = store.decide_many(ids, decision, args.reviewer, args.reason)
            print(f"{decision}: {done} fact(s)" + (f", {skipped} already decided or unknown" if skipped else ""))
        facts = store.pending(args.service)
        print(f"\n{len(facts)} pending fact(s)\n")
        for f in facts:
            unit = f" {f.unit}" if f.unit else ""
            change = f"   (graph holds: {f.old_value})" if f.old_value and f.old_value != f.value_text else ""
            print(f"  #{f.staged_id:<5} {f.fact_id:<52} {f.value_text[:44]}{unit}{change}")
        print("\nstatus counts:", store.counts())
    finally:
        store.close()
    return 0


def _write_graph(args: argparse.Namespace) -> int:
    """Approved facts into Neo4j. Needs the database (for the facts) and Neo4j running."""
    dsn = _dsn(args)
    if dsn is None:
        print("writing the graph needs the database: add --db")
        return 1
    from app.core.graph.writer import GraphWriter, neo4j_from_dotenv

    conf = neo4j_from_dotenv(REPO_ROOT / ".env")
    if conf is None:
        print(f"no NEO4J_PASSWORD in {REPO_ROOT / '.env'}")
        return 1
    writer = GraphWriter(dsn, *conf)
    try:
        if args.graph_summary:
            for k, v in writer.summary().items():
                print(f"  {k:<22} {v}")
            return 0
        report = writer.write_approved(service_id=args.service, dry_run=args.dry_run)
        if args.dry_run:
            print(f"dry run: {report.new} approved fact(s) would be written {report.by_predicate}")
            return 0
        print(f"written: {report.new} new, {report.changed} changed, {report.same} unchanged")
        print(f"by predicate: {report.by_predicate}")
        for staged_id, why in report.failed:
            print(f"  FAILED #{staged_id}: {why}")
        print("\ngraph now:")
        for k, v in writer.summary().items():
            print(f"  {k:<22} {v}")
    finally:
        writer.close()
    return 1 if report.failed else 0


def _restage(args: argparse.Namespace) -> int:
    """Re-process a stored model reply with the current code. No model call, no tokens."""
    dsn = _dsn(args)
    if dsn is None:
        print("--restage needs the database: add --db")
        return 1
    from app.core.extraction.restage import restage

    try:
        new_id, facts, dropped, staged = restage(dsn, args.restage, REPO_ROOT, dry_run=args.dry_run,
                                                 service_id=args.service)
    except LookupError as e:
        print(e)
        return 1
    for f in facts:
        unit = f" {f.unit}" if f.unit else ""
        num = f"  = {f.value_num:g}{unit}" if f.value_num is not None else ""
        print(f"  {f.fact_id:<54} {f.value_text[:48]}{num}")
    for d in dropped:
        print(f"  DROPPED {d['fact_id']} = {str(d.get('value', ''))[:40]!r}: {d['reason']}")
        if d.get("evidence"):
            print(f"          quoted: {d['evidence'][:110]!r}")
    print(f"\n{len(facts)} fact(s), {len(dropped)} dropped, re-processed from extraction {args.restage}"
          " (no model call)")
    print("dry run: nothing saved" if args.dry_run else f"saved: extraction {new_id}, {staged} new pending fact(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.core.acquisition", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=Path, default=DEFAULT_SEEDS)
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="where state, archive and logs go")
    ap.add_argument("--browser", action="store_true", help="render JavaScript (slower); default is plain HTTP")
    ap.add_argument("--http-only", action="store_true", help="plain HTTP fetch (the default)")
    ap.add_argument("--min-interval", type=float, default=2.0, help="seconds between requests to one host")
    ap.add_argument("--report", action="store_true", help="print the measured change profile and exit")
    ap.add_argument("--check-seeds", action="store_true", help="validate the seed list and exit")
    ap.add_argument("--db", action="store_true", help="also log to PostgreSQL, using the repo .env")
    ap.add_argument("--database-url", help="PostgreSQL DSN (overrides --db)")
    ap.add_argument("--discover", metavar="URL", help="list and score the pages this URL links to")
    ap.add_argument("--depth", type=int, default=1, help="link levels to follow from --discover URL")
    ap.add_argument("--limit", type=int, default=40, help="most candidates to collect")
    ap.add_argument("--no-screen", action="store_true", help="list links only, without fetching each")
    ap.add_argument("--extract-file", type=Path, metavar="MD", help="extract facts from an archived .md page")
    ap.add_argument("--service", help="service id for --extract-file, e.g. svc:passport")
    ap.add_argument("--agency", default="", help="agency name for --extract-file")
    ap.add_argument("--source-url", help="the page's URL, for provenance")
    ap.add_argument("--model", default="gpt-4o-mini", help="model name for --extract-file")
    ap.add_argument("--llm-base-url", default="https://api.openai.com/v1",
                    help="OpenAI-compatible endpoint (OpenAI, Groq, Ollama, a gateway)")
    ap.add_argument("--reasoning-effort", choices=["none", "low", "medium", "high"],
                    help="how much the model may think first (fewer output tokens when low or none)")
    ap.add_argument("--review", action="store_true", help="list pending facts (needs --db)")
    ap.add_argument("--approve", metavar="IDS", help="approve staged fact ids, comma separated, or 'all'")
    ap.add_argument("--reject", metavar="IDS", help="reject staged fact ids, comma separated, or 'all'")
    ap.add_argument("--reason", default="", help="why, recorded in the audit trail (needed to reject)")
    ap.add_argument("--reviewer", default="malindu", help="who is deciding, for the audit trail")
    ap.add_argument("--write-graph", action="store_true",
                    help="write approved facts to Neo4j (needs --db; add --dry-run to preview)")
    ap.add_argument("--graph-summary", action="store_true", help="print what Neo4j holds (needs --db)")
    ap.add_argument("--restage", type=int, metavar="EXTRACTION_ID",
                    help="re-process a stored model reply with the current code (needs --db; no model call)")
    ap.add_argument("--show-prompt", action="store_true", help="print the extraction input; no model call")
    ap.add_argument("--dry-run", action="store_true", help="extract and print, but do not save")
    args = ap.parse_args(argv)

    if args.check_seeds:
        s = summarise(load_seeds(args.seeds))
        print(f"{s['pages']} pages, {s['verified']} verified")
        for k, v in sorted(s["per_service"].items()):
            print(f"  {k:<28}{v}")
        return 0
    if args.report:
        print(report_mod.render(report_mod.profile(report_mod.load_rows(args.root / "changes.jsonl"))))
        return 0
    if args.restage:
        return _restage(args)
    if args.write_graph or args.graph_summary:
        return _write_graph(args)
    if args.review or args.approve or args.reject:
        return _review(args)
    if args.extract_file:
        return _extract(args)
    if args.discover:
        return asyncio.run(_discover(args))
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
