"""Stage 2 with a fake model: ontology, grounding, fact ids and staging. No network, no key."""

import json
import re
import uuid
from pathlib import Path

import pytest

from app.core.extraction.extractor import MAX_PAGE_CHARS, extract_page
from app.core.extraction.llm import LLMError, LLMReply
from app.core.extraction.ontology import FACT_ID, is_grounded, parse_amount, slug

# Wording taken from the live passport page (immigration.gov.lk/pages_e.php?id=8).
PAGE = """
* [Home](https://www.immigration.gov.lk/index_e.php)
* [Visa Fees](https://www.immigration.gov.lk/pages_e.php?id=45)

## Issue of Passports

What are the documents required to be submitted along with the completed application form ?

1. Photo studio acknowledgement
2. Original Birth Certificate of the applicant with a photocopy.
3. Original National Identity Card of the applicant with a photocopy

What are the delivery times for All-Countries Passport ? Normal Basis - 30 working days
Urgent Basis - Same day

What are the processing fees for All-Countries Passport ? Normal Basis - LKR. 10,000.00
Urgent Basis - LKR.20,000.00
"""

URL = "https://www.immigration.gov.lk/pages_e.php?id=8"
WHEN = "2026-10-10T08:00:00+00:00"


class FakeLLM:
    def __init__(self, payload=None, text=None, error=None):
        self.payload, self.text, self.error = payload, text, error
        self.seen = None

    def complete(self, system, user):
        self.seen = (system, user)
        if self.error:
            raise LLMError(self.error)
        text = self.text if self.text is not None else json.dumps(self.payload)
        return LLMReply(text, prompt_tokens=1200, completion_tokens=180, model="fake-model")


def good_payload():
    return {
        "agency": "Department of Immigration and Emigration",
        "agency_evidence": None,
        "fees": [
            {"qualifier": "Normal", "amount_text": "LKR. 10,000.00",
             "evidence": "Normal Basis - LKR. 10,000.00"},
            {"qualifier": "urgent", "amount_text": "LKR.20,000.00",
             "evidence": "Urgent Basis - LKR.20,000.00"},
            {"qualifier": "invented", "amount_text": "LKR 99,999",   # not on the page
             "evidence": "Express Basis - LKR 99,999"},
        ],
        "documents": [
            {"name": "Original Birth Certificate of the applicant with a photocopy",
             "condition": None,
             "evidence": "Original Birth Certificate of the applicant with a photocopy."},
            {"name": "Original National Identity Card", "condition": None,
             "evidence": "Original National Identity Card of the applicant with a photocopy"},
        ],
        "prerequisites": [
            {"description": "Photo studio acknowledgement", "provided_by": "Authorized photo studio",
             "evidence": "Photo studio acknowledgement"},
        ],
        "processing_times": [
            {"qualifier": "normal", "text": "30 working days", "evidence": "Normal Basis - 30 working days"},
        ],
    }


def run(llm, text=PAGE, service="svc:passport"):
    return extract_page(text, service_id=service, agency="Department of Immigration and Emigration",
                        source_url=URL, retrieved_at=WHEN, llm=llm)


# ---------------------------------------------------------------------- normalising
@pytest.mark.parametrize("text,value,unit", [
    ("LKR. 10,000.00", 10000.0, "LKR"),
    ("LKR.20,000.00", 20000.0, "LKR"),
    ("LKR 3500.00", 3500.0, "LKR"),
    ("Rs. 20,000", 20000.0, "LKR"),
    ("Normal Basis - LKR. 10,000.00", 10000.0, "LKR"),
    ("Free of charge", 0.0, "LKR"),
    ("30 working days", 30.0, None),
    ("see the office", None, None),
])
def test_four_fee_formats_give_one_value(text, value, unit):
    assert parse_amount(text) == (value, unit)


def test_slugs_match_the_contract_pattern():
    assert slug("Original Birth Certificate of the applicant") == "original_birth_certificate_of_the"
    assert slug("Normal / Urgent!") == "normal_urgent"
    assert FACT_ID.match(f"svc:passport:fee:{slug('Minor - Normal')}")


def test_grounding_ignores_markdown_and_punctuation_but_not_invention():
    assert is_grounded("Normal Basis - LKR. 10,000.00", PAGE)
    assert is_grounded("**Normal Basis**: LKR 10,000.00", PAGE)
    assert not is_grounded("Express Basis - LKR 99,999", PAGE)
    assert not is_grounded("fee", PAGE)  # too short to prove anything


# ----------------------------------------------------------------------- extraction
def test_facts_are_built_with_position_based_ids():
    r = run(FakeLLM(good_payload()))
    ids = {f.fact_id for f in r.facts}
    assert "svc:passport:fee:normal" in ids
    assert "svc:passport:fee:urgent" in ids
    assert "svc:passport:processing_time:normal" in ids
    assert "svc:passport:prerequisite:photo_studio_acknowledgement" in ids
    assert all(FACT_ID.match(i) for i in ids)
    assert all(f.status == "pending" for f in r.facts)
    fee = next(f for f in r.facts if f.fact_id == "svc:passport:fee:normal")
    assert (fee.value_text, fee.value_num, fee.unit) == ("LKR. 10,000.00", 10000.0, "LKR")
    assert fee.source_url == URL and fee.retrieved_at == WHEN


def test_a_fact_the_page_does_not_state_is_dropped_not_stored():
    r = run(FakeLLM(good_payload()))
    assert not any("invented" in f.fact_id for f in r.facts)
    assert "svc:passport:fee:invented" in [d["fact_id"] for d in r.dropped]


def test_agency_without_a_quote_is_not_kept():
    r = run(FakeLLM(good_payload()))
    assert not any(f.predicate == "agency" for f in r.facts)
    assert any(d["fact_id"] == "svc:passport:agency" for d in r.dropped)


def test_real_token_counts_are_carried():
    r = run(FakeLLM(good_payload()))
    assert (r.prompt_tokens, r.completion_tokens, r.model) == (1200, 180, "fake-model")


def test_menus_are_not_sent_to_the_model():
    llm = FakeLLM(good_payload())
    run(llm)
    _, user = llm.seen
    assert "Visa Fees" not in user and "Original Birth Certificate" in user


def test_repeated_position_keeps_the_first_statement():
    p = good_payload()
    p["fees"].append({"qualifier": "normal", "amount_text": "LKR 3500.00",
                      "evidence": "Normal Basis - LKR. 10,000.00"})
    r = run(FakeLLM(p))
    fees = [f for f in r.facts if f.fact_id == "svc:passport:fee:normal"]
    assert len(fees) == 1 and fees[0].value_text == "LKR. 10,000.00"


def test_unparseable_model_output_is_an_error_not_a_crash():
    r = run(FakeLLM(text="Sure! Here are the facts:"))
    assert r.facts == [] and "schema" in r.error


def test_provider_failure_is_reported():
    r = run(FakeLLM(error="HTTP 401: bad key"))
    assert r.facts == [] and "401" in r.error


def test_long_pages_are_truncated_and_flagged():
    r = run(FakeLLM({}), text="word " * MAX_PAGE_CHARS)
    assert r.truncated


def test_bad_service_id_is_refused():
    with pytest.raises(ValueError):
        run(FakeLLM({}), service="passport")


# ------------------------------------------------------------------------- staging
REPO_ROOT = Path(__file__).resolve().parents[4]


def _dsn():
    from app.core.acquisition.db import dsn_from_dotenv

    dsn = dsn_from_dotenv(REPO_ROOT / ".env")
    if dsn is None:
        pytest.skip("no .env with POSTGRES_* settings")
    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=3) as conn:
            conn.execute("SELECT 1 FROM c2.staged_facts LIMIT 1")
    except Exception as e:  # not running, or 003_c2_extraction.sql not applied
        pytest.skip(f"c2 extraction tables not reachable: {type(e).__name__}")
    return dsn


def test_staged_facts_are_saved_once_and_not_duplicated():
    import psycopg

    from app.core.extraction.staging import StagingStore

    dsn = _dsn()
    host = f"pgtest-{uuid.uuid4().hex[:8]}.invalid"
    url = f"https://{host}/pages_e.php?id=8"
    result = extract_page(PAGE, service_id="svc:passport", agency="Immigration", source_url=url,
                          retrieved_at=WHEN, llm=FakeLLM(good_payload()))
    store = StagingStore(dsn)
    try:
        _, first = store.save(url, result, "svc:passport", "Immigration")
        _, again = store.save(url, result, "svc:passport", "Immigration")
        assert first == len(result.facts) > 0
        assert again == 0  # same fact, same value, same source: not queued twice
        ext = store.conn.execute(
            "SELECT prompt_tokens, completion_tokens, dropped FROM c2.extractions "
            "WHERE source_url = %s ORDER BY extraction_id LIMIT 1", (url,)).fetchone()
        assert ext == (1200, 180, 2)  # the invented fee and the agency that has no quote
        row = store.conn.execute(
            "SELECT value_num, unit, status FROM c2.staged_facts "
            "WHERE source_url = %s AND fact_id = 'svc:passport:fee:normal'", (url,)).fetchone()
        assert (float(row[0]), row[1], row[2]) == (10000.0, "LKR", "pending")
    finally:
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute("DELETE FROM c2.extractions WHERE source_url = %s", (url,))
            conn.execute("DELETE FROM c2.pages WHERE url = %s", (url,))
            conn.execute("DELETE FROM c2.sources WHERE host = %s", (host,))
        store.close()


# ================================================== variants, stable ids, prerequisites
from app.core.extraction.vocabulary import (  # noqa: E402
    canonical_document,
    canonical_qualifier,
    canonical_variant,
)

VARIANT_PAGE = """
## Ordinary passports
Normal Basis - LKR. 10,000.00
Original National Identity Card of the applicant with a photocopy
Original Birth Certificate of the applicant with a photocopy.

## Minor applicants
Normal Basis - LKR. 3,000.00
Original Birth Certificate of the applicant with a photocopy.
National Identity Card of the parent with a photocopy.

## Lost passports
Rs. 20,000 in addition to the passport fee
A request letter from the Ministry of Foreign Affairs
Current passport with a photocopy of the Bio data page
"""


def variant_payload():
    return {
        "fees": [
            {"qualifier": "Normal Basis", "variant": "Ordinary Passports", "kind": "base",
             "amount_text": "LKR. 10,000.00", "evidence": "Normal Basis - LKR. 10,000.00"},
            {"qualifier": "Normal Basis", "variant": "Underage / Minor applicants", "kind": "base",
             "amount_text": "LKR. 3,000.00", "evidence": "Normal Basis - LKR. 3,000.00"},
            {"qualifier": "additional", "variant": "Lost passport", "kind": "surcharge",
             "amount_text": "Rs. 20,000 in addition to the passport fee",
             "evidence": "Rs. 20,000 in addition to the passport fee"},
        ],
        "documents": [
            {"name": "Original National Identity Card", "variant": "ordinary",
             "evidence": "Original National Identity Card of the applicant with a photocopy"},
            {"name": "Original Birth Certificate", "variant": "ordinary",
             "evidence": "Original Birth Certificate of the applicant with a photocopy."},
            {"name": "Original Birth Certificate", "variant": "minor",
             "evidence": "Original Birth Certificate of the applicant with a photocopy."},
            {"name": "Current passport with a photocopy of the Bio data page", "variant": "lost",
             "evidence": "Current passport with a photocopy of the Bio data page"},
            {"name": "A request letter from the Ministry of Foreign Affairs", "variant": "lost",
             "evidence": "A request letter from the Ministry of Foreign Affairs"},
        ],
    }


def run_variants(payload=None):
    return run(FakeLLM(payload or variant_payload()), text=VARIANT_PAGE)


@pytest.mark.parametrize("name,key,service", [
    ("Original National Identity Card of the applicant with a photocopy", "national_identity_card", "svc:nic"),
    ("Birth Certificate with a photocopy.", "birth_certificate", "svc:birth_certificate"),
    ("Consular Birth Certificate and Citizenship Registration Certificate",
     "consular_birth_certificate", None),
    ("Parent’s Passport (with photocopies of data page)", "passport", "svc:passport"),
    ("Photo studio acknowledgement", "photo_studio_acknowledgement", None),
    ("A request letter from the Parliament", "request_letter", None),
])
def test_documents_map_to_a_canonical_key_and_service(name, key, service):
    c = canonical_document(name)
    assert (c.key, c.service_id) == (key, service)


def test_unknown_documents_fall_back_to_the_pages_own_words():
    c = canonical_document("Original of the technical inspection report for the vehicle")
    assert c.service_id is None and FACT_ID.match(f"svc:x:document:{c.key}")
    assert len(c.key) <= 40 and not c.key.endswith("_")


@pytest.mark.parametrize("label,variant", [
    ("Ordinary Passports", "ordinary"),
    ("Underage / Minor applicants (3 years)", "minor"),
    ("Lost passport within one year of issue", "lost"),
    ("Diplomatic Passports", "diplomatic"),
    ("All", None),
    (None, None),
])
def test_variants_use_one_label_for_one_case(label, variant):
    assert canonical_variant(label) == variant


@pytest.mark.parametrize("label,q", [
    ("Normal Basis", "normal"), ("normal", "normal"), ("Urgent Basis", "urgent"),
    ("Same day", "urgent"), ("", "standard"),
])
def test_fee_labels_are_canonical(label, q):
    assert canonical_qualifier(label) == q


def test_the_same_label_on_two_variants_no_longer_collides():
    r = run_variants()
    fees = {f.fact_id: f for f in r.facts if f.predicate == "fee"}
    assert fees["svc:passport:fee:ordinary_normal"].value_num == 10000.0
    assert fees["svc:passport:fee:minor_normal"].value_num == 3000.0
    assert not any("already holds" in d["reason"] for d in r.dropped)


def test_a_surcharge_is_marked_and_not_a_base_fee():
    r = run_variants()
    lost = next(f for f in r.facts if f.fact_id.startswith("svc:passport:fee:lost_"))
    assert lost.detail["kind"] == "surcharge" and lost.value_num == 20000.0
    base = next(f for f in r.facts if f.fact_id == "svc:passport:fee:ordinary_normal")
    assert base.detail["kind"] == "base"


def test_one_document_on_several_variants_is_one_fact_listing_them():
    r = run_variants()
    birth = [f for f in r.facts if f.fact_id == "svc:passport:document:birth_certificate"]
    assert len(birth) == 1
    assert birth[0].detail["applies_to"] == ["ordinary", "minor"]


def test_documents_that_are_services_become_prerequisite_links():
    r = run_variants()
    pre = {f.fact_id: f for f in r.facts if f.predicate == "prerequisite"}
    assert pre["svc:passport:prerequisite:national_identity_card"].detail["requires_service"] == "svc:nic"
    birth = pre["svc:passport:prerequisite:birth_certificate"]
    assert birth.detail["requires_service"] == "svc:birth_certificate"
    assert birth.detail["origin"] == "derived_from_document"
    assert birth.detail["applies_to"] == ["ordinary", "minor"]


def test_a_service_is_never_its_own_prerequisite():
    r = run_variants()  # "Current passport ... Bio data page" is a passport document
    assert "svc:passport:prerequisite:passport" not in {f.fact_id for f in r.facts}
    assert any(f.fact_id == "svc:passport:document:passport" for f in r.facts)


def test_ids_do_not_depend_on_how_the_model_words_a_label():
    a = variant_payload()
    b = variant_payload()
    b["fees"][0].update(qualifier="normal", variant="ordinary passport applicants")
    b["documents"][0]["name"] = "National Identity Card (original)"
    ids_a = {f.fact_id for f in run_variants(a).facts}
    ids_b = {f.fact_id for f in run_variants(b).facts}
    assert ids_a == ids_b
