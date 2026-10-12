"""The seed registry: which pages are monitored, for which service and agency."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import yaml

# Same pattern as the shared contract (contracts/naming.md): svc:<slug>
SERVICE_ID = re.compile(r"^svc:[a-z0-9_]+$")


@dataclass(frozen=True)
class Seed:
    url: str
    service: str | None  # None when the page is not labelled: the services are read from the page
    agency: str
    note: str = ""
    verified: bool = False  # opened in a browser and confirmed to state a fee, documents or a prerequisite


def load_seeds(path: Path) -> list[Seed]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    seeds = []
    for entry in data.get("seeds", []):
        service = entry.get("service")
        if service is not None and not SERVICE_ID.match(service):
            raise ValueError(f"service id must look like svc:passport, got {service!r}")
        seeds.append(Seed(
            url=entry["url"].strip(),
            service=service,
            agency=entry["agency"],
            note=str(entry.get("note") or ""),
            verified=bool(entry.get("verified", False)),
        ))
    urls = [s.url for s in seeds]
    dupes = [u for u, n in Counter(urls).items() if n > 1]
    if dupes:
        raise ValueError(f"duplicate seed URLs: {dupes}")
    return seeds


def summarise(seeds: list[Seed]) -> dict:
    return {
        "pages": len(seeds),
        "verified": sum(s.verified for s in seeds),
        "per_service": dict(Counter(s.service or "(read from the page)" for s in seeds)),
        "per_agency": dict(Counter(s.agency for s in seeds)),
    }
