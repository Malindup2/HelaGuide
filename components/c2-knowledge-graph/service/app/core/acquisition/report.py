"""The measured change profile: what real pages actually do between crawls."""

from __future__ import annotations

import json
from pathlib import Path


def load_rows(changes_path: Path) -> list[dict]:
    path = Path(changes_path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def profile(rows: list[dict]) -> dict:
    """Summarise observations. NEW is excluded: a first sighting is not a change."""
    runs = sorted({r.get("run_id") or r["ts"] for r in rows})
    per_kind: dict[str, int] = {}
    per_url: dict[str, list[str]] = {}
    for r in rows:
        if r["change"] == "NEW":
            continue
        per_kind[r["change"]] = per_kind.get(r["change"], 0) + 1
        per_url.setdefault(r["url"], []).append(r["change"])

    observations = sum(per_kind.values())
    content = per_kind.get("CONTENT_CHANGED", 0)
    structure = per_kind.get("STRUCTURE_CHANGED", 0)
    changed = content + structure
    never = [u for u, ks in per_url.items() if all(k == "UNCHANGED" for k in ks)]
    return {
        "runs": len(runs),
        "pages": len(per_url),
        "observations": observations,
        "per_kind": per_kind,
        "real_change_rate": changed / observations if observations else 0.0,
        "structural_share_of_changes": structure / changed if changed else 0.0,
        "unreachable": per_kind.get("UNREACHABLE", 0),
        "never_changed_pages": len(never),
    }


def render(p: dict) -> str:
    if not p["observations"]:
        return "No repeat observations yet: run at least two passes."
    lines = [
        f"MEASURED CHANGE PROFILE: {p['runs']} runs, {p['pages']} pages, "
        f"{p['observations']} observations (first sightings excluded)",
        "",
        f"  {'change type':<20}{'count':>8}{'share':>10}",
        "  " + "-" * 38,
    ]
    for kind, n in sorted(p["per_kind"].items(), key=lambda kv: -kv[1]):
        lines.append(f"  {kind:<20}{n:>8}{n / p['observations'] * 100:>9.1f}%")
    lines += [
        "",
        f"  real change rate (content or structure): {p['real_change_rate'] * 100:.1f}%",
        f"  structural share of real changes:        {p['structural_share_of_changes'] * 100:.1f}%",
        f"  pages that never changed:                {p['never_changed_pages']} / {p['pages']}",
    ]
    return "\n".join(lines)
