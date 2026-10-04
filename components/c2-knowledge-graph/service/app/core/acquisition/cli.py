"""Command line for stage 1.

    python -m app.core.acquisition --check-seeds
    python -m app.core.acquisition --http-only          # one monitoring pass
    python -m app.core.acquisition --report             # measured change profile

Run it from components/c2-knowledge-graph/service/ with the crawl extra installed:
    pip install -e ".[dev,crawl]"
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.core.acquisition import report as report_mod
from app.core.acquisition.fetch import USER_AGENT, Crawl4AIFetcher, PoliteFetcher
from app.core.acquisition.monitor import JsonlRunLog, PageResult, run_pass
from app.core.acquisition.ratelimit import HostRateLimiter
from app.core.acquisition.robots import RobotsPolicy
from app.core.acquisition.seeds import load_seeds, summarise
from app.core.acquisition.store import SnapshotStore

C2_ROOT = Path(__file__).resolve().parents[4]
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


async def _run(args: argparse.Namespace) -> int:
    seeds = load_seeds(args.seeds)
    if not seeds:
        print(f"no seeds in {args.seeds}")
        return 1
    inner = Crawl4AIFetcher(http_only=not args.browser)
    fetcher = PoliteFetcher(inner, RobotsPolicy(USER_AGENT), HostRateLimiter(args.min_interval))
    store, log = SnapshotStore(args.root), JsonlRunLog(args.root)
    print(f"monitoring {len(seeds)} pages [{'browser' if args.browser else 'http-only'}]\n")
    try:
        summary = await run_pass(seeds, fetcher, store, log, on_page=_print_page)
    finally:
        await inner.aclose()
    print(f"\nrun {summary.run_id}")
    for kind, n in sorted(summary.counts.items(), key=lambda kv: -kv[1]):
        print(f"  {kind:<18} {n}")
    print(f"\n{len(summary.to_extract)} page(s) need extraction")
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
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
