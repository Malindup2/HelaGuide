"""
Service names and aliases (English, Sinhala script, Singlish). The `fact` contract carries no
service name, so C3 keeps its own small list. It is C3-private data, used only to recognise
which service a citizen is talking about.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.core.lexicon import has_sinhala
from app.core.util import fmt_value

PREDICATE_PHRASE = {
    "fee": "fee", "document": "required document", "processing_time": "processing time",
    "agency": "responsible agency", "prerequisite": "prerequisite", "eligibility": "eligibility",
}


@dataclass
class ServiceInfo:
    service_id: str
    name_en: str
    agency: str
    aliases_en: list[str] = field(default_factory=list)
    aliases_si: list[str] = field(default_factory=list)
    aliases_singlish: list[str] = field(default_factory=list)
    default_qualifiers: dict[str, str] = field(default_factory=dict)

    @property
    def profile_text(self) -> str:
        also = ", ".join(self.aliases_en)
        return f"{self.name_en}. Also called: {also}. Handled by {self.agency}."

    def strip_aliases(self, text: str) -> str:
        """The text without this service's own name, so 'death certificate fee' reads as just 'fee'."""
        out = text or ""
        for alias in sorted(self.aliases_en + self.aliases_si + self.aliases_singlish + [self.name_en],
                            key=len, reverse=True):
            a = alias.strip()
            if not a:
                continue
            if has_sinhala(a):
                out = out.replace(a, " ")
            else:
                out = re.sub(rf"(?<![A-Za-z0-9]){re.escape(a)}(?![A-Za-z0-9])", " ", out, flags=re.I)
        return re.sub(r"\s+", " ", out).strip()

    def alias_hit(self, *texts: str) -> bool:
        blob = " ".join(t for t in texts if t).lower()
        for alias in self.aliases_en + self.aliases_si + self.aliases_singlish:
            a = alias.lower().strip()
            if not a:
                continue
            if has_sinhala(a):
                if a in blob:
                    return True
            elif re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", blob):
                return True
        return False


class ServiceCatalog:
    def __init__(self, path: Path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.services: dict[str, ServiceInfo] = {s["service_id"]: ServiceInfo(**s) for s in data["services"]}

    def get(self, service_id: str) -> ServiceInfo | None:
        return self.services.get(service_id)

    def all(self) -> list[ServiceInfo]:
        return list(self.services.values())

    def describe(self, service_id: str, predicate: str, qualifier: str | None, value, unit: str | None) -> str:
        """Plain-English sentence for a fact, used for embedding and for display."""
        svc = self.get(service_id)
        name = svc.name_en if svc else service_id.split(":", 1)[-1].replace("_", " ")
        q = (qualifier or "").replace("_", " ").strip()
        v = fmt_value(value, unit)
        if predicate == "fee":
            return f"{name}: {q + ' ' if q else ''}fee is {v}"
        if predicate == "processing_time":
            u = unit or "days"
            return f"{name}: {q + ' ' if q else ''}processing time is {value} {u}"
        if predicate == "document":
            return f"{name}: required document - {value}"
        if predicate == "agency":
            return f"{name}: handled by {value}"
        if predicate == "prerequisite":
            return f"{name}: prerequisite - {value}"
        if predicate == "eligibility":
            return f"{name}: eligibility - {value}"
        return f"{name}: {predicate} {q} {v}"
