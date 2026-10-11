"""Controlled vocabulary: what the model's free wording is mapped onto before ids are built.

The model reads pages; it does not name things. A fact_id has to be the same on every run,
so names, variants and fee labels are canonicalised here, in code, from a small list that is
reviewed and grows by decision. Anything not in the list falls back to the page's own words,
cut on word boundaries, so nothing is lost and the unknowns are easy to find and promote.

A document that is itself a service (a birth certificate, an NIC) carries that service's id.
That is the link the graph needs: "svc:passport requires svc:nic".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.extraction.ontology import normalise_for_match, slug


@dataclass(frozen=True)
class Canonical:
    key: str
    service_id: str | None = None  # set when the document is produced by a service


# Ordered: the first pattern found in the document name wins, so specific names come first.
# Patterns are matched on lowercase letters and digits with single spaces (see normalise_for_match).
_DOCUMENTS: tuple[tuple[str, Canonical], ...] = (
    ("consular birth certificate", Canonical("consular_birth_certificate")),
    ("birth certificate", Canonical("birth_certificate", "svc:birth_certificate")),
    ("national identity card", Canonical("national_identity_card", "svc:nic")),
    ("identity card", Canonical("national_identity_card", "svc:nic")),
    ("marriage certificate", Canonical("marriage_certificate")),
    ("death certificate", Canonical("death_certificate")),
    ("divorce certificate", Canonical("divorce_certificate")),
    ("dual citizenship certificate", Canonical("dual_citizenship_certificate")),
    ("certificate of adoption", Canonical("adoption_certificate")),
    ("police clearance", Canonical("police_clearance_report", "svc:police_clearance")),
    ("police report", Canonical("police_report")),
    ("complaint made to the police", Canonical("police_report")),
    ("photo studio acknowledg", Canonical("photo_studio_acknowledgement")),
    ("photograph", Canonical("photographs")),
    ("application form", Canonical("application_form")),
    ("educational certificate", Canonical("educational_certificate")),
    ("academic certificate", Canonical("educational_certificate")),
    ("service certificate", Canonical("service_certificate")),
    ("consent letter", Canonical("consent_letter")),
    ("request letter", Canonical("request_letter")),
    ("court order", Canonical("court_order")),
    ("affidavit", Canonical("affidavit")),
    ("grama niladhari", Canonical("grama_niladhari_letter")),
    ("passport", Canonical("passport", "svc:passport")),
)

# Words that mark a variant of a service; checked in this order against the model's label.
_VARIANTS: tuple[tuple[str, str], ...] = (
    ("diplomatic", "diplomatic"),
    ("official", "official"),
    ("minor", "minor"),
    ("underage", "minor"),
    ("child", "minor"),
    ("lost", "lost"),
    ("stolen", "lost"),
    ("replacement", "replacement"),
    ("damaged", "replacement"),
    ("identification", "identification_certificate"),
    ("dual", "dual_citizen"),
    ("ordinary", "ordinary"),
)
_NO_VARIANT = {"", "all", "general", "any", "none", "standard", "common"}


def canonical_document(name: str) -> Canonical:
    """Map a document or step name to its canonical key (and service, when it is one)."""
    text = f" {normalise_for_match(name)} "
    for needle, canon in _DOCUMENTS:
        if f" {needle}" in text:  # at the start of a word, so "nic" never matches "technical"
            return canon
    return Canonical(slug(" ".join(normalise_for_match(name).split()[:5]), 40) or "other")


def canonical_variant(label: str | None) -> str | None:
    s = slug(label or "", 60)
    if s in _NO_VARIANT:
        return None
    for needle, variant in _VARIANTS:
        if needle in s:
            return variant
    return slug(s.replace("_", " "), 30) or None


def canonical_qualifier(label: str | None) -> str:
    """Fee and time labels: normal, urgent, or the page's own short word."""
    s = slug(label or "", 60)
    if "urgent" in s or "same_day" in s or "express" in s:
        return "urgent"
    if "normal" in s:
        return "normal"
    s = re.sub(r"_(basis|fee|fees|charge|charges)$", "", s)
    return slug(s.replace("_", " "), 30) or "standard"
