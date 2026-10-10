"""One monitoring pass: fetch every seed, fingerprint it, classify it, log the result."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from app.core.acquisition.fetch import Fetcher
from app.core.acquisition.fingerprint import ChangeKind, Fingerprint, classify, fingerprint
from app.core.acquisition.seeds import Seed
from app.core.acquisition.store import Snapshot, SnapshotStore

# Fewer characters than this after noise stripping usually means the page is rendered by
# JavaScript and an HTTP-only fetch saw an empty shell. It is flagged, not hidden.
THIN_CONTENT_CHARS = 200


@dataclass
class PageResult:
    run_id: str
    url: str
    service: str
    agency: str
    kind: ChangeKind
    detail: dict = field(default_factory=dict)
    fingerprint: Fingerprint | None = None
    status: int | None = None
    error: str = ""
    tls_relaxed: bool = False
    duration_ms: int = 0
    fetched_at: str = ""
    source_type: str = "html"

    @property
    def needs_extraction(self) -> bool:
        """Only pages that are new or changed ever reach the language model."""
        return self.kind in (ChangeKind.NEW, ChangeKind.CONTENT_CHANGED, ChangeKind.STRUCTURE_CHANGED)


@dataclass
class RunSummary:
    run_id: str
    started_at: str
    finished_at: str
    counts: dict[str, int]
    pages: list[PageResult]

    @property
    def to_extract(self) -> list[PageResult]:
        return [p for p in self.pages if p.needs_extraction]


class RunLog(Protocol):
    def page(self, result: PageResult) -> None: ...
    def finish(self, summary: RunSummary) -> None: ...


class JsonlRunLog:
    """Append-only logs: one line per page per run, and one line per run.

    changes.jsonl keeps the prototype's record shape (ts, url, change) with run metadata
    added, so earlier measurements and new ones can be read together.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.changes_path = self.root / "changes.jsonl"
        self.runs_path = self.root / "runs.jsonl"

    def _append(self, path: Path, record: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def page(self, r: PageResult) -> None:
        self._append(self.changes_path, {
            "ts": r.fetched_at, "run_id": r.run_id, "url": r.url, "service": r.service,
            "agency": r.agency, "change": r.kind.value, "status": r.status,
            "tls_relaxed": r.tls_relaxed, "duration_ms": r.duration_ms,
            "source_type": r.source_type,
            **({"error": r.error} if r.error else {}), **r.detail,
        })

    def finish(self, s: RunSummary) -> None:
        self._append(self.runs_path, {
            "run_id": s.run_id, "started_at": s.started_at, "finished_at": s.finished_at,
            "pages": len(s.pages), "counts": s.counts, "to_extract": len(s.to_extract),
        })


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def run_pass(
    seeds: list[Seed],
    fetcher: Fetcher,
    store: SnapshotStore,
    log: RunLog,
    on_page: Callable[[PageResult], None] | None = None,
) -> RunSummary:
    """Fetch and classify every seed, one at a time.

    Pages are fetched sequentially. Politeness (robots.txt, per-host spacing) is the
    fetcher's job; the pass itself stays simple and its log order is deterministic.

    A change is written to the run log BEFORE the stored fingerprint advances, so the
    log is the durable hand-off to extraction: a page that changed is never silently
    forgotten just because a later step failed.
    """
    run_id = uuid.uuid4().hex[:12]
    started = _now()
    pages: list[PageResult] = []
    counts: dict[str, int] = {}

    for seed in seeds:
        fetched = await fetcher.fetch(seed.url)
        base = dict(run_id=run_id, url=seed.url, service=seed.service, agency=seed.agency,
                    status=fetched.status, tls_relaxed=fetched.tls_relaxed,
                    duration_ms=fetched.duration_ms, fetched_at=fetched.fetched_at or _now(),
                    source_type=fetched.source_type)

        if not fetched.ok:
            result = PageResult(kind=ChangeKind.UNREACHABLE, error=fetched.error, **base)
        else:
            cur = fingerprint(fetched.text, fetched.html)
            prev = store.latest(seed.url)
            verdict = classify(prev.fingerprint if prev else None, cur)
            detail = dict(verdict.detail)
            if cur.char_count < THIN_CONTENT_CHARS:
                detail["thin_content"] = True
            result = PageResult(kind=verdict.kind, detail=detail, fingerprint=cur, **base)

        log.page(result)  # durable first
        if result.fingerprint is not None:
            store.save(
                Snapshot(seed.url, result.fingerprint, result.fetched_at, result.status,
                         result.tls_relaxed),
                fetched.html, fetched.text,
                archive=result.kind is not ChangeKind.UNCHANGED,
                pdf=fetched.content if fetched.source_type == "pdf" else None,
            )
        counts[result.kind.value] = counts.get(result.kind.value, 0) + 1
        pages.append(result)
        if on_page:
            on_page(result)

    summary = RunSummary(run_id, started, _now(), counts, pages)
    log.finish(summary)
    return summary
