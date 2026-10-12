"""What to leave out: the editable rules in research/data/exclusions.yaml, applied in code.

Two moments. Before a link is followed, its address and text are matched (cheap, nothing is
fetched). After a page is fetched, its own text decides (a page that is nearly empty, or that is
only a mission and vision statement). Each exclusion carries a reason, so the report can say
what was skipped and why, and an admin can change the rules instead of asking for a fix.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.core.acquisition.discover import score_text, strip_menus

DEFAULTS = {
    "link_patterns": [
        "vacanc", "recruit", "tender|procurement|procument", "circular", "gall?ery",
        r"\bmission\b|\bvision\b|\bobjectives?\b", r"\bhistory\b|past commissioner", r"\bcadre\b",
    ],
    "min_text_chars": 150,
    "about_headings": ["mission", "vision", "goal", "objective", "history", "overview", "welcome"],
}

_HEADING = re.compile(r"^\s*(?:#{1,6}\s+|\*\*)(.+?)(?:\*\*)?\s*$", re.M)


@dataclass
class Exclusions:
    link: list[tuple[str, re.Pattern]] = field(default_factory=list)
    min_chars: int = 150
    about: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path | None = None) -> "Exclusions":
        data = dict(DEFAULTS)
        if path and Path(path).exists():
            try:
                data.update(yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})
            except yaml.YAMLError:
                pass  # a broken rules file must not stop a crawl: fall back to the defaults
        link = []
        for p in data.get("link_patterns", []):
            try:
                link.append((p, re.compile(p, re.I)))
            except re.error:
                continue
        return cls(link, int(data.get("min_text_chars", 150)),
                   [str(x).lower() for x in data.get("about_headings", [])])

    def link_reason(self, url: str, label: str = "") -> str | None:
        target = f"{url} {label}"
        for raw, pat in self.link:
            if pat.search(target):
                return f"matches the rule '{raw}'"
        return None

    def page_reason(self, md: str) -> str | None:
        """Why a fetched page is not worth keeping, or None when it is."""
        body = strip_menus(md or "")
        text = re.sub(r"[#*>|_`\[\]()\-]+", " ", re.sub(r"\(https?://[^)]*\)", "", body))
        if len(" ".join(text.split())) < self.min_chars:
            return f"almost no readable text (under {self.min_chars} characters)"
        heads = [h.strip(" *#").lower() for h in _HEADING.findall(body) if h.strip(" *#")]
        sig = score_text(md or "")
        if heads and not sig.score and all(any(a in h for a in self.about) for h in heads):
            return "only mission, vision, history or welcome text"
        return None
