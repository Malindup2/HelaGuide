"""
Hand-written word lists (no training). They cover English, Sinhala script and Singlish
(Sinhala typed in English letters). Tamil is out of scope.

These lists are deliberately small and easy to read: they exist so every decision the
grounding step makes can be explained in one sentence.
"""
from __future__ import annotations

import re

from app.core.util import norm_text, numbers_in

SINHALA_RE = re.compile(r"[\u0D80-\u0DFF]")

# Singlish markers: words that are almost never English but are common in romanised Sinhala.
SINGLISH_TOKENS = {
    "eka", "eke", "ekak", "ekata", "ekate", "ekai", "ekeh", "kiwwa", "kiwwe", "kiwwama", "kiyala",
    "kiyanna", "gaanawa", "gaana", "gaanuwa", "gaththa", "gaththe", "gannawa", "ganna", "wage", "nemei",
    "nemeyi", "thiyenawa", "tiyenawa", "wuna", "una", "wenas", "denawa", "dunna", "ayeth", "ilwwa",
    "ilwwe", "mata", "mage", "oya", "oyala", "eth", "saha", "hari", "naha", "nae", "dawas", "karanna",
    "karala", "aluth", "puluwan", "wayasa", "daruwage", "ayeth", "gewanna", "gewwa", "welawa", "mokakda",
    "kohomada", "ape", "api", "kala", "thibba", "tibba", "wunath", "eken", "walata", "ganne", "denna",
}

# What each kind of discrepancy sounds like. Counted once per distinct word.
PREDICATE_WORDS: dict[str, set[str]] = {
    "fee": {"fee", "fees", "charge", "charged", "charges", "cost", "costs", "price", "paid", "pay",
            "payment", "rupees", "rs", "lkr", "usd", "amount", "money", "expensive",
            "gaana", "gaanawa", "gaanuwa", "gaththa", "mudala", "salli", "gewanna", "gewwa",
            "ගාස්තු", "ගාස්තුව", "රුපියල්", "මුදල", "අය කළා", "ගත්තා"},
    "document": {"document", "documents", "certificate", "certificates", "copy", "letter", "form",
                 "photo", "photos", "photograph", "photographs", "asked", "ask", "asking", "bring", "brought", "required",
                 "needed", "submit", "submitted", "affidavit", "police report", "proof",
                 "pathra", "patra", "sahathika", "sahathikaya", "ilwwa", "ilwwe",
                 "ලේඛන", "සහතිකය", "පත්‍රය", "ඉල්ලුවා", "ඉල්ලා"},
    "processing_time": {"days", "day", "weeks", "week", "months", "month", "took", "long", "delay",
                        "delayed", "waiting", "waited", "wait", "ready", "processing", "collect", "time",
                        "dawas", "dina", "sathi", "welawa", "ගියා", "දින", "සති", "මාස"},
    "agency": {"located", "location", "address", "moved", "branch", "which office", "wrong office"},
    "prerequisite": {"prerequisite", "before", "first", "beforehand", "earlier"},
    "eligibility": {"eligible", "eligibility", "age", "allowed", "qualify", "qualified", "old",
                    "wayasa", "wayasa", "puluwan", "වයස", "සුදුසුකම"},
}
PRED_WEIGHT = {"fee": 1.0, "document": 1.0, "processing_time": 1.0, "agency": 1.0, "prerequisite": 0.7,
               "eligibility": 1.0}

# Words that mark a variant of a service. Keyed by the qualifier used in the fact id.
QUALIFIER_PHRASES: dict[str, list[str]] = {
    "normal": ["normal", "ordinary", "regular", "standard"],
    "one_day": ["one day", "oneday", "one-day", "same day", "1 day", "urgent", "express"],
    "minor": ["minor", "child", "children", "kid", "daughter", "son's", "under 16", "below 16", "baby"],
    "minor_normal": ["minor", "child", "children", "kid", "under 16", "below 16"],
    "lost_replacement": ["lost", "stolen", "replacement", "replace", "re-issue", "reissue"],
    "replacement": ["lost", "stolen", "replacement", "replace", "damaged", "duplicate", "re-issue", "reissue"],
    "first_issue": ["first", "new card", "first time", "new nic", "first issue"],
    "certified_copy": ["certified copy", "certified", "copy", "extract"],
    "late_registration": ["late", "unregistered", "delayed registration"],
    "first_extension": ["first extension", "first", "initial"],
    "second_extension": ["second extension", "second", "further"],
    "online": ["online"],
    "application": ["application"],
    "per_certificate": ["per certificate", "each certificate", "translate", "translation"],
    "police_report_lost": ["police", "lost", "stolen"],
    "icao_photograph": ["icao", "photograph", "photo"],
    "grama_niladhari_certification": ["grama niladhari", "gn ", "gramasevaka"],
    "birth_certificate": ["birth certificate", "birth cert"],
    "nic": ["nic", "identity card", "id card"],
    "photographs": ["photograph", "photo"],
    "application_form": ["application form", "form"],
    "informant_nic": ["informant", "nic", "identity card"],
    "parents_marriage_certificate": ["marriage certificate", "parents"],
    "medical_certificate": ["medical", "doctor"],
    "passport": ["passport"],
    "extension_form": ["extension form", "form"],
    "declaration": ["declaration"],
    "original_certificate": ["original"],
    "age": ["age", "years", "old"],
    "applicant": ["citizen", "applicant"],
    "tourist_visa_holder": ["tourist visa"],
    "issuing": [],
}

SUPPORT_CUES = ["was correct", "is correct", "that was right", "was right", "as you said", "as your guide said",
                "as listed", "same as", "no change", "has not changed", "matches", "it was fine", "was ok",
                "that is correct", "that was correct", "charged correctly", "ඒක හරි", "හරි"]
NEGATIONS = ["not ", "n't", " no ", "different", "wrong", "more than", "higher", "less than", "instead",
             "but ", "however", "did not", "didn't", "nemei", "naha", "නොවේ", "නෑ"]

TIME_WORDS = ["yesterday", "today", "this morning", "last week", "last month", "ago", "on monday",
              "on tuesday", "on wednesday", "on thursday", "on friday", "on saturday", "on sunday",
              "last night", "iye", "ada", "ඊයේ", "අද", "පසුගිය"]
PLACE_WORDS = ["office", "counter", "branch", "department", "secretariat", "registrar", "immigration",
               "battaramulla", "colombo", "kandy", "galle", "jaffna", "kurunegala", "matara", "gampaha",
               "කාර්යාල", "දෙපාර්තමේන්තු"]


def has_sinhala(text: str) -> bool:
    return bool(SINHALA_RE.search(text or ""))


def detect_language(text: str) -> str:
    """'si' (Sinhala script, possibly with English words), 'mixed' (Singlish) or 'en'."""
    if has_sinhala(text):
        return "si"
    tokens = re.findall(r"[a-z]+", (text or "").lower())
    hits = sum(1 for t in tokens if t in SINGLISH_TOKENS)
    return "mixed" if hits >= 1 else "en"


def needs_translation(language: str | None, raw_text: str) -> bool:
    lang = language or detect_language(raw_text)
    return lang != "en"


def detect_predicate(texts: list[str]) -> tuple[str | None, dict[str, float]]:
    """Which kind of fact is the citizen talking about? Returns (best or None, scores)."""
    blob = " ".join(t for t in texts if t).lower()
    tokens = set(re.findall(r"[a-z]+", blob))
    scores: dict[str, float] = {}
    for pred, words in PREDICATE_WORDS.items():
        s = 0.0
        for w in words:
            if " " in w or has_sinhala(w):
                hit = w in blob
            else:
                hit = w in tokens
            if hit:
                s += PRED_WEIGHT[pred]
        scores[pred] = s
    # a currency amount next to a number is strong evidence of a fee
    if re.search(r"(?i)\b(rs|rupees|lkr|usd)\b\.?\s*\d|\d[\d,]*\s*(rupees|rs\b|lkr|usd)", blob):
        scores["fee"] += 1.0
    best = max(scores.values())
    winners = [p for p, v in scores.items() if v == best]
    if best <= 0 or len(winners) != 1:
        return None, scores
    return winners[0], scores


def qualifier_hits(text: str, qualifiers: list[str]) -> set[str]:
    """Which of these qualifiers does the text mention?"""
    t = f" {text.lower()} "
    hits = set()
    for q in qualifiers:
        for phrase in QUALIFIER_PHRASES.get(q, []):
            if re.search(rf"(?<![a-z0-9]){re.escape(phrase.strip())}(?![a-z0-9])", t):
                hits.add(q)
                break
    return hits


def has_negation(text: str) -> bool:
    t = f" {text.lower()} "
    return any(n in t for n in NEGATIONS)


def has_support_cue(text: str) -> bool:
    t = text.lower()
    return any(c in t for c in SUPPORT_CUES)


def extract_claimed(text_en: str, raw_text: str, stored_num: float | None, hint) -> tuple[float | None, str | None]:
    """The value the citizen says is right. Hint first, then the numbers in the text.

    If the text mentions the stored value as well ("it was 12,000, not 11,000"), the
    stored value is what the citizen is quoting back at us, so the OTHER number is the claim.
    """
    if hint is not None and hint != "":
        try:
            num = float(str(hint).replace(",", ""))
            return num, str(hint)
        except ValueError:
            return None, str(hint)
    nums = numbers_in(text_en) or numbers_in(raw_text)
    if not nums:
        return None, None
    if stored_num is not None and len(nums) > 1:
        others = [n for n in nums if n != stored_num]
        if others:
            nums = others
    return nums[0], f"{nums[0]:g}"


def infer_kind(text_en: str, claimed_num: float | None, stored_num: float | None) -> str:
    """'support' if the citizen says the stored information was right, else 'dispute'."""
    neg = has_negation(text_en)
    if has_support_cue(text_en) and not neg:
        return "support"
    if claimed_num is not None and stored_num is not None and claimed_num == stored_num and not neg:
        return "support"
    return "dispute"


def specificity_features(text_en: str, raw_text: str, claimed_num: float | None, has_visit_date: bool) -> dict[str, bool]:
    blob = f"{text_en} {raw_text}".lower()
    return {
        "value": claimed_num is not None or bool(numbers_in(blob)),
        "when": has_visit_date or any(w in blob for w in TIME_WORDS),
        "where": any(w in blob for w in PLACE_WORDS),
        "detail": len((text_en or "").split()) >= 12,
    }


def clean_for_embedding(text: str) -> str:
    return norm_text(text) or (text or "")
