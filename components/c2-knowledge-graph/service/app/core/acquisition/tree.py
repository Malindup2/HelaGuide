"""The link tree: which page was found on which page.

Discovery used to forget this the moment it wrote its candidate list. The tree keeps it, across
runs, in <crawl root>/tree.json, so the pages can be shown nested under the page they were found
on. Nothing here fetches anything.

    {"nodes": {url: {"parent": url | null, "label": str, "signals": "FD-",
                     "type": "html"|"pdf", "chars": int, "found": "2026-10-11"}}}
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

NAME = "tree.json"


def load(root: Path) -> dict:
    p = Path(root) / NAME
    if not p.exists():
        return {"nodes": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data.get("nodes"), dict) else {"nodes": {}}
    except (OSError, ValueError):
        return {"nodes": {}}


def merge(root: Path, start: str, rows: list[dict], found: str | None = None) -> dict:
    """Add the pages of one discovery run. A page keeps the parent it was first found under;
    its label, signals and size are refreshed."""
    data = load(root)
    nodes = data["nodes"]
    today = found or date.today().isoformat()
    nodes.setdefault(start, {"parent": None, "label": "", "signals": "", "type": "html",
                             "chars": 0, "found": today})
    for r in rows:
        url = r["url"]
        old = nodes.get(url, {})
        nodes[url] = {
            "parent": old.get("parent") or r.get("discovered_from") or start,
            "label": r.get("label") or old.get("label", ""),
            "signals": r.get("signals") or old.get("signals", ""),
            "type": r.get("source_type") or old.get("type", "html"),
            "chars": r.get("chars") or old.get("chars", 0),
            "found": old.get("found", today),
        }
    p = Path(root) / NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return data


def children_of(nodes: dict) -> dict[str | None, list[str]]:
    out: dict[str | None, list[str]] = {}
    for url, n in nodes.items():
        out.setdefault(n.get("parent"), []).append(url)
    for lst in out.values():
        lst.sort()
    return out
