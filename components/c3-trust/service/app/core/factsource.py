"""
Where C3 gets facts from. C3 never touches Neo4j; it only reads what C2 serves.

  FileFactSource : reads a JSON file shaped like C2's `fact` contract. Used for PP1, so the
                   component runs with no dependency on anyone else's service or data.
  HttpFactSource : calls C2's GET /v1/facts/{fact_id}. Used at integration time.
                   (C2 has no "list all facts" route, so it can only look facts up one by one.)

Switching between them is the C3_FACT_SOURCE setting; nothing else changes.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Protocol

import httpx

log = logging.getLogger(__name__)


class FactSource(Protocol):
    def list_facts(self) -> list[dict]: ...
    def get_fact(self, fact_id: str) -> dict | None: ...


class FileFactSource:
    def __init__(self, path: Path):
        self.path = Path(path)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.facts: dict[str, dict] = {f["fact_id"]: f for f in data["facts"]}

    def list_facts(self) -> list[dict]:
        return list(self.facts.values())

    def get_fact(self, fact_id: str) -> dict | None:
        return self.facts.get(fact_id)

    def publish_updates(self, updates_path: Path) -> list[dict]:
        """Simulate C2 publishing new versions of some facts (used by the demo)."""
        data = json.loads(Path(updates_path).read_text(encoding="utf-8"))
        changed = []
        for f in data["facts"]:
            self.facts[f["fact_id"]] = f
            changed.append(f)
        return changed


class HttpFactSource:
    def __init__(self, base_url: str, client: httpx.Client | None = None):
        self.base = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=httpx.Timeout(5.0))

    def list_facts(self) -> list[dict]:
        log.warning("C2 offers no list route; HttpFactSource can only look facts up by id")
        return []

    def get_fact(self, fact_id: str) -> dict | None:
        try:
            r = self.client.get(f"{self.base}/v1/facts/{fact_id}")
        except httpx.HTTPError as exc:
            log.warning("C2 unreachable for %s: %s", fact_id, type(exc).__name__)
            return None
        return r.json() if r.status_code == 200 else None


def build_source(settings) -> FileFactSource | HttpFactSource:
    if settings.fact_source == "http":
        return HttpFactSource(settings.c2_url)
    return FileFactSource(settings.data_dir / "c2_facts.json")
