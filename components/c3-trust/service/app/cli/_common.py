"""Shared helpers for the command-line tools. Run them from components/c3-trust/service."""
from __future__ import annotations

import argparse
import sys

from app.core.config import C3Settings
from app.core.pipeline import Pipeline


def utf8() -> None:
    """Make Sinhala text print correctly in the Windows console."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--sqlite", action="store_true",
                   help="use an in-memory SQLite database instead of PostgreSQL (no Docker needed)")
    p.add_argument("--db", help="database URL (default: C3_DATABASE_URL, i.e. the PostgreSQL from docker-compose.c3.yml)")
    p.add_argument("--embedding", choices=["sbert", "hash"],
                   help="sbert = the real pretrained model (default); hash = a tiny stand-in for plumbing checks only")


def settings_from_args(args) -> C3Settings:
    over: dict = {}
    if getattr(args, "sqlite", False):
        over["database_url"] = "sqlite://"
    elif getattr(args, "db", None):
        over["database_url"] = args.db
    if getattr(args, "embedding", None):
        over["embedding_backend"] = args.embedding
        if args.embedding == "hash":      # the stand-in produces small similarities: loosen the thresholds
            over.update(tau_f=0.42, delta_f=0.05, tau_miss_cos=0.15)
    return C3Settings(**over)


def build(args, reset: bool = True) -> Pipeline:
    from sqlalchemy.exc import OperationalError, ProgrammingError
    s = settings_from_args(args)
    try:
        return Pipeline.build(s, reset=reset)
    except OperationalError as exc:
        print("\nCould not connect to the database:", mask_url(s.database_url))
        print("  - Is Docker Desktop running?")
        print("  - Did you start the database?   docker compose -f docker-compose.c3.yml up -d   (run in components/c3-trust)")
        print("  - Or run without Docker:        add  --sqlite  to this command")
        print("\nTechnical detail:", str(exc.orig).strip().splitlines()[0] if exc.orig else exc)
        sys.exit(1)
    except (RuntimeError, ProgrammingError) as exc:
        print("\nProblem:", exc)
        sys.exit(1)


def mask_url(url: str) -> str:
    if "@" in url and "://" in url:
        head, tail = url.split("://", 1)
        creds, host = tail.rsplit("@", 1)
        user = creds.split(":")[0]
        return f"{head}://{user}:****@{host}"
    return url


def banner(text: str, ch: str = "=") -> None:
    print("\n" + ch * 78)
    print(text)
    print(ch * 78)


def table(headers: list[str], rows: list[list], max_width: int = 46) -> str:
    cells = [[str(c) if len(str(c)) <= max_width else str(c)[: max_width - 1] + "…" for c in r] for r in rows]
    widths = [max(len(h), *(len(r[i]) for r in cells)) if cells else len(h) for i, h in enumerate(headers)]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    sep = "  ".join("-" * w for w in widths)
    body = "\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths)) for r in cells)
    return f"{line}\n{sep}\n{body}"
