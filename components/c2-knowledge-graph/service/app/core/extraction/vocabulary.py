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
    ("ordination certificate", Canonical("ordination_certificate")),
    ("samanera certificate", Canonical("ordination_certificate")),
    ("commissioner of probation", Canonical("probation_commissioner_letter")),
    ("authorization letter", Canonical("authorization_letter")),
    ("authorisation letter", Canonical("authorization_letter")),
    ("temporary travel document", Canonical("temporary_travel_document")),
    ("tin certificate", Canonical("tin_certificate", "svc:taxpayer_identification_number_tin")),
    ("taxpayer identification number", Canonical("tin_certificate", "svc:taxpayer_identification_number_tin")),
    ("passport", Canonical("passport", "svc:passport")),
)

# A document naming someone OTHER than the applicant is never the applicant's own
# prerequisite -- "Photocopies of valid Passports of Directors" on a company's TIN
# registration page is not a reason to tell an individual citizen to get a passport first.
# Real bug found 18 Oct 2026: svc:taxpayer_identification_number_tin derived "requires
# svc:passport" from exactly this sentence.
_THIRD_PARTY = re.compile(
    r"(?i)\bof\s+(directors?|the\s+company|the\s+deceased|the\s+decease|shareholders?|"
    r"partners?|the\s+applicant'?s?\s+(?:spouse|parent|guardian))\b")


def names_a_third_party(text: str) -> bool:
    return bool(_THIRD_PARTY.search(text or ""))

# Words that mark a variant of a service; checked in this order against the model's label.
_VARIANTS: tuple[tuple[str, str], ...] = (
    ("diplomatic", "diplomatic"),
    ("official", "official"),
    ("minor", "minor"),
    ("underage", "minor"),
    ("child", "minor"),
    ("below", "minor"),  # "below 16 years of age" is how the pages say minor
    ("lost", "lost"),
    ("stolen", "lost"),
    ("replacement", "replacement"),
    ("first_time", "first_issue"),
    ("first_issue", "first_issue"),
    ("amend", "amended"),
    ("correction", "amended"),
    ("damaged", "replacement"),
    ("identification", "identification_certificate"),
    ("dual", "dual_citizen"),
    ("ordinary", "ordinary"),
    ("all_countries", "ordinary"),  # "valid for all countries" is the ordinary passport
)
_NO_VARIANT = {"", "all", "general", "any", "none", "standard", "common"}


def canonical_document(name: str) -> Canonical:
    """Map a document or step name to its canonical key (and service, when it is one)."""
    text = f" {normalise_for_match(name)} "
    for needle, canon in _DOCUMENTS:
        if f" {needle}" in text:  # at the start of a word, so "nic" never matches "technical"
            return canon
    return Canonical(slug(" ".join(normalise_for_match(name).split()[:5]), 40) or "other")


def known_variant(text: str | None) -> str | None:
    """A variant only if the text names one we know. Safe to run over a whole quote."""
    s = slug(text or "", 200)
    for needle, variant in _VARIANTS:
        if needle in s:
            return variant
    return None


def canonical_variant(label: str | None) -> str | None:
    s = slug(label or "", 60)
    if s in _NO_VARIANT:
        return None
    return known_variant(s) or slug(s.replace("_", " "), 30) or None


def canonical_qualifier(label: str | None) -> str:
    """Fee and time labels: normal, urgent, or the page's own short word."""
    s = slug(label or "", 60)
    if "one_day" in s or "oneday" in s:
        return "one_day"  # a service mode of its own, not the same as urgent
    if "urgent" in s or "same_day" in s or "express" in s:
        return "urgent"
    if "normal" in s:
        return "normal"
    s = re.sub(r"_(basis|fee|fees|charge|charges)$", "", s)
    return slug(s.replace("_", " "), 30) or "standard"


_WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                 "eight": 8, "nine": 9, "ten": 10, "twelve": 12}
_AMOUNT_UNIT = re.compile(
    r"(?P<n>\d+|" + "|".join(_WORD_NUMBERS) + r")\s*(?P<u>year|month|day|week)s?")


def canonical_condition(label: str | None) -> str | None:
    """'Validity period for 3 years' -> '3y'; 'within one year of issue' -> 'within_1y'."""
    text = normalise_for_match(label or "")
    if not text or text in _NO_VARIANT:
        return None
    m = _AMOUNT_UNIT.search(text)
    if m:
        n = m.group("n")
        n = str(_WORD_NUMBERS.get(n, int(n) if n.isdigit() else n))  # "06" and "6" are one number
        span = f"{n}{m.group('u')[0]}"
        # "has exceeded 06 months" and "does not obtain within six months" both mean: late.
        late = re.search(r"\b(exceed\w*|after|more than|over|beyond|late|fail\w*)\b", text) or \
            re.search(r"\b(not|never|without)\b.*\b(within|before)\b", text)
        if late:
            return f"after_{span}"
        if re.search(r"\b(within|before|less than|under)\b", text):
            return f"within_{span}"
        return span
    # Why a penalty is charged: a few reasons recur across agencies.
    if re.search(r"\b(failure|fail\w*|not obtain\w*|did not apply|late|prescribed time)\b", text):
        return "late_application"
    if re.search(r"\b(false|forged|fake|incorrect|misleading)\b", text):
        return "false_information"
    if re.search(r"\b(two occasions|twice|repeated|second time|more than once)\b", text):
        return "repeat_submission"
    return slug(" ".join(text.split()[:3]), 30) or None
