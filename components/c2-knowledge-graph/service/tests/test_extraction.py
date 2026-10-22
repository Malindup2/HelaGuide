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


# ============================== conditions: validity periods and time windows (real page)
from app.core.extraction.vocabulary import canonical_condition  # noqa: E402

CONDITION_PAGE = """
What are the processing fees for All-Countries Passport (below 16 years of age) ?
Validity period for 3 years
Normal Basis - LKR. 3,000.00
Urgent Basis - LKR. 9,000.00
Validity period for 10 years
Normal Basis - LKR. 10,000.00
Urgent Basis - LKR. 20,000.00
Passports lost within one year of issue - A fine of Rs. 20,000 in addition to the passport fee.
Passports lost after one year of issue - A fine of Rs. 15,000 in addition to the passport fee.
"""


def fee(q, variant, cond, amount, evidence, kind="base"):
    return {"qualifier": q, "variant": variant, "condition": cond, "kind": kind,
            "amount_text": amount, "evidence": evidence}


def condition_payload():
    minor = "All-Countries Passport (below 16 years of age)"
    return {"fees": [
        fee("Normal Basis", minor, "Validity period for 3 years", "LKR. 3,000.00",
            "Normal Basis - LKR. 3,000.00"),
        fee("Urgent Basis", minor, "Validity period for 3 years", "LKR. 9,000.00",
            "Urgent Basis - LKR. 9,000.00"),
        fee("Normal Basis", minor, "Validity period for 10 years", "LKR. 10,000.00",
            "Normal Basis - LKR. 10,000.00"),
        fee("Urgent Basis", minor, "Validity period for 10 years", "LKR. 20,000.00",
            "Urgent Basis - LKR. 20,000.00"),
        fee("fine", "lost passport", "within one year of issue", "Rs. 20,000",
            "Passports lost within one year of issue - A fine of Rs. 20,000 in addition to the passport fee.",
            "surcharge"),
        fee("fine", "lost passport", "after one year of issue", "Rs. 15,000",
            "Passports lost after one year of issue - A fine of Rs. 15,000 in addition to the passport fee.",
            "surcharge"),
    ]}


@pytest.mark.parametrize("label,expected", [
    ("Validity period for 3 years", "3y"),
    ("Validity period for 10 years", "10y"),
    ("Passports lost within one year of issue", "within_1y"),
    ("lost after one year of issue", "after_1y"),
    ("valid for six months", "6m"),
    (None, None),
])
def test_conditions_become_short_stable_tokens(label, expected):
    assert canonical_condition(label) == expected


def test_page_wording_for_minors_and_all_countries_maps_to_known_variants():
    assert canonical_variant("All-Countries Passport (below 16 years of age)") == "minor"
    assert canonical_variant("All-Countries Passport") == "ordinary"


def test_fees_that_differ_only_by_validity_or_window_are_all_kept():
    r = run(FakeLLM(condition_payload()), text=CONDITION_PAGE)
    ids = {f.fact_id: f for f in r.facts if f.predicate == "fee"}
    assert ids["svc:passport:fee:minor_normal_3y"].value_num == 3000.0
    assert ids["svc:passport:fee:minor_normal_10y"].value_num == 10000.0
    assert ids["svc:passport:fee:minor_urgent_3y"].value_num == 9000.0
    assert ids["svc:passport:fee:minor_urgent_10y"].value_num == 20000.0
    assert ids["svc:passport:fee:lost_fine_within_1y"].value_num == 20000.0
    assert ids["svc:passport:fee:lost_fine_after_1y"].value_num == 15000.0
    assert not any("already holds" in d["reason"] for d in r.dropped)


def test_unlisted_ordination_and_authorisation_documents_are_canonical():
    assert canonical_document("Samanera certificate or Higher Ordination certificate").key == "ordination_certificate"
    assert canonical_document("acceptable authorization letter given by the parents").key == "authorization_letter"
    assert canonical_document("A letter from the Commissioner of Probation").key == "probation_commissioner_letter"


# ================================= tolerance: one bad item must not cost the page
def test_a_malformed_item_is_dropped_and_the_rest_of_the_page_is_kept():
    p = good_payload()
    p["fees"].insert(1, {"qualifier": "urgent", "amount_text": None, "evidence": "x"})  # no amount
    p["documents"].append("not an object at all")
    r = run(FakeLLM(p))
    assert r.error == ""
    ids = {f.fact_id for f in r.facts}
    assert "svc:passport:fee:normal" in ids and "svc:passport:fee:urgent" in ids
    reasons = " ".join(d["reason"] for d in r.dropped)
    assert "did not match the schema" in reasons and "fees[1]" in str(r.dropped)


def test_a_missing_or_null_label_does_not_invalidate_the_item():
    p = good_payload()
    p["fees"][0]["qualifier"] = None
    p["fees"][0].pop("variant", None)
    r = run(FakeLLM({"fees": [{"qualifier": None, "amount_text": "LKR. 10,000.00",
                               "evidence": "Normal Basis - LKR. 10,000.00"}]}))
    assert [f.fact_id for f in r.facts if f.predicate == "fee"] == ["svc:passport:fee:standard"]


def test_a_non_object_reply_is_an_error():
    r = run(FakeLLM(text="[1, 2, 3]"))
    assert r.facts == [] and "schema" in r.error


# ================================================ the client waits out a provider spike
def test_client_retries_a_busy_provider_then_succeeds(monkeypatch):
    import httpx

    from app.core.extraction import llm as llm_mod

    calls, sleeps = [], []

    def fake_post(url, **kw):
        calls.append(url)
        if len(calls) < 3:
            return httpx.Response(503, text="high demand", request=httpx.Request("POST", url))
        return httpx.Response(200, request=httpx.Request("POST", url), json={
            "choices": [{"message": {"content": "{}"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2}, "model": "m"})

    monkeypatch.setattr(llm_mod.httpx, "post", fake_post)
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: sleeps.append(s))
    reply = llm_mod.OpenAICompatClient("k", "m", "https://x.test/v1").complete("s", "u")
    assert reply.text == "{}" and len(calls) == 3
    assert sleeps == [5, 15]  # long enough to outlast a spike, not a one-second blip


def test_client_does_not_retry_a_bad_key(monkeypatch):
    import httpx

    from app.core.extraction import llm as llm_mod

    calls = []

    def fake_post(url, **kw):
        calls.append(url)
        return httpx.Response(401, text="bad key", request=httpx.Request("POST", url))

    monkeypatch.setattr(llm_mod.httpx, "post", fake_post)
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: None)
    with pytest.raises(LLMError, match="401"):
        llm_mod.OpenAICompatClient("k", "m", "https://x.test/v1").complete("s", "u")
    assert len(calls) == 1


# ==================== the same item gets the same id whether or not the model labels it
def test_variant_is_read_from_the_quote_when_the_model_leaves_it_empty():
    quote = "Passports lost after one year of issue - A fine of Rs. 15,000 in addition to the passport fee."
    labelled = {"fees": [fee("fine", "lost passport", "after one year of issue", "Rs. 15,000", quote,
                              "surcharge")]}
    unlabelled = {"fees": [fee("fine", None, "after one year of issue", "Rs. 15,000", quote,
                                "surcharge")]}
    a = run(FakeLLM(labelled), text=CONDITION_PAGE)
    b = run(FakeLLM(unlabelled), text=CONDITION_PAGE)
    ids_a = [f.fact_id for f in a.facts if f.predicate == "fee"]
    ids_b = [f.fact_id for f in b.facts if f.predicate == "fee"]
    assert ids_a == ids_b == ["svc:passport:fee:lost_fine_after_1y"]


def test_an_unlabelled_plain_fee_is_not_given_an_invented_variant():
    quote = "Normal Basis - LKR. 3,000.00"
    r = run(FakeLLM({"fees": [fee("Normal Basis", None, None, "LKR. 3,000.00", quote)]}),
            text=CONDITION_PAGE)
    assert [f.fact_id for f in r.facts if f.predicate == "fee"] == ["svc:passport:fee:normal"]


def test_a_dropped_item_keeps_the_quote_the_model_gave():
    r = run(FakeLLM({"fees": [fee("normal", None, None, "LKR 1", "Express Basis - LKR 1")]}),
            text=CONDITION_PAGE)
    assert r.dropped and r.dropped[0]["evidence"] == "Express Basis - LKR 1"


# ===== a real sentence run on into the next line is still grounded; an invention is not
REAL_PAGE = """
  * Passports lost within one year of issue - A fine of Rs. 20,000 in addition to the passport fee.
  * Passports lost after one year of issue - A fine of Rs. 15,000 in addition to the passport fee.
(This fine is charged only if the relevant validity period of the passport has not lapsed.)
These passports are valid for all countries and the validity period is 10 years unless otherwise specified in the passport. This passport is issued to VVIPs.
"""


def test_a_quote_that_runs_on_past_a_real_sentence_is_grounded_by_that_sentence():
    quote = ("Passports lost within one year of issue - A fine of Rs. 20,000 in addition to the "
             "passport fee. This fine is charged only if the validity period has not lapsed.")
    assert is_grounded(quote, REAL_PAGE, value="Rs. 20,000")


def test_the_real_sentence_must_actually_hold_the_value():
    quote = "Passports lost within one year of issue - A fine of Rs. 20,000 in addition to the passport fee."
    assert not is_grounded(quote, REAL_PAGE, value="Rs. 25,000")  # a number the sentence lacks


def test_an_invented_sentence_is_never_grounded_even_with_a_matching_value():
    quote = "Passports lost within two years of issue - A fine of Rs. 20,000 in addition to the passport fee."
    assert not is_grounded(quote, REAL_PAGE, value="Rs. 20,000")


def test_without_a_value_only_the_whole_quote_counts():
    quote = "Passports lost within one year of issue - A fine of Rs. 20,000 in addition to the passport fee. Extra tail."
    assert not is_grounded(quote, REAL_PAGE)


def test_extraction_keeps_a_real_fee_whose_quote_ran_into_the_next_line():
    quote = ("Passports lost within one year of issue - A fine of Rs. 20,000 in addition to the "
             "passport fee. This fine is charged only if it has not lapsed.")
    p = {"fees": [fee("fine", "lost passport", "within one year of issue", "Rs. 20,000", quote,
                      "surcharge")]}
    r = run(FakeLLM(p), text=REAL_PAGE)
    assert [f.fact_id for f in r.facts] == ["svc:passport:fee:lost_fine_within_1y"]
    assert r.dropped == []


# ================= lessons from the NIC page: table rows, short values, self-links
NIC_PAGE = """
| 1  | Fee for issuance of a new National Identity card in place of a lost National Identity card. [(Notice on revision of fees charged) ](https://drp.gov.lk/en/assets/downloads/fees-english.pdf).   | Rs.1000.00  |
| 1. Fee for issuance of amended National Identity card [(Notice on revision of fees charged) ](https://drp.gov.lk/en/assets/downloads/fees-english.pdf)  | Rs.500.00  |
Under the One day service, National Identity cards are issued for people who need to obtain the National Identity cards urgently.
Forward the application for the National Identity card through the Grama Niladhari.
Birth certificate or extract of the birth registry
"""


def test_a_table_row_with_a_link_between_label_and_price_is_grounded():
    quote = ("Fee for issuance of a new National Identity card in place of a lost National "
             "Identity card. Rs.1000.00")
    assert is_grounded(quote, NIC_PAGE, value="Rs.1000.00")


def test_a_table_row_quote_still_needs_the_right_price():
    quote = ("Fee for issuance of a new National Identity card in place of a lost National "
             "Identity card. Rs.1500.00")
    assert not is_grounded(quote, NIC_PAGE, value="Rs.1500.00")


def test_an_invented_part_of_a_table_row_quote_is_not_grounded():
    quote = "Fee for issuance of a brand new Smart card in place of a lost card. Rs.1000.00"
    assert not is_grounded(quote, NIC_PAGE, value="Rs.1000.00")


def test_a_short_value_is_grounded_when_every_word_is_in_the_quote():
    quote = "Under the One day service, National Identity cards are issued for people who need to obtain the National Identity cards urgently."
    assert is_grounded(quote, NIC_PAGE, value="One day")
    assert not is_grounded(quote, NIC_PAGE, value="Two weeks")


def test_a_service_is_never_its_own_stated_prerequisite():
    p = {"prerequisites": [{"description": "Forward the application for the National Identity card through the Grama Niladhari",
                            "evidence": "Forward the application for the National Identity card through the Grama Niladhari."}],
         "documents": [{"name": "Birth certificate or extract of the birth registry",
                        "evidence": "Birth certificate or extract of the birth registry"}]}
    r = run(FakeLLM(p), text=NIC_PAGE, service="svc:nic")
    pre = {f.fact_id: f for f in r.facts if f.predicate == "prerequisite"}
    own = pre["svc:nic:prerequisite:national_identity_card"]
    assert "requires_service" not in own.detail            # no link to itself
    assert pre["svc:nic:prerequisite:birth_certificate"].detail["requires_service"] == "svc:birth_certificate"


def test_nic_service_modes_and_variants_get_stable_ids():
    from app.core.extraction.vocabulary import canonical_qualifier, canonical_variant

    assert canonical_variant("First time applicants") == "first_issue"
    assert canonical_variant("Amending a National Identity card") == "amended"
    assert canonical_variant("Dual citizen") == "dual_citizen"
    assert canonical_qualifier("One day service") == "one_day"
    assert canonical_qualifier("Normal service") == "normal"


# ============ NIC page, second run: postage, duplicate conditions, one-line table rows
NIC_PAGE_2 = """
| 1. Fee for issuance of amended National Identity card [(Notice on revision of fees charged) ](https://drp.gov.lk/en/assets/downloads/fees-english.pdf)  | Rs.500.00  |
| 2. Fee for sending National Identity card by registered post under normal service.   | Rs.120.00  |
| 3. If the period between date of obtaining dual citizenship and the date of applying for the National Identity card has exceeded 06 months   | Rs.2500.00  |
| 6  |  Under Section 19(2) of the Citizenship Act, penalty for an applicant who does not obtain a National Identity card within six months from the date of issue of the Dual Citizenship certificate.   |  Rs.2500/-  |
"""


def test_a_one_line_quote_with_a_link_in_the_table_row_is_grounded():
    quote = "Fee for issuance of amended National Identity card Rs.500.00"
    assert is_grounded(quote, NIC_PAGE_2, value="Rs.500.00")
    assert not is_grounded("Fee for issuance of amended National Identity card Rs.900.00",
                           NIC_PAGE_2, value="Rs.900.00")


def test_tokens_cannot_be_stitched_from_far_apart_parts_of_a_page():
    far = NIC_PAGE_2 + ("\nfiller words here " * 40) + "\nRs.777.00 is the sum"
    assert not is_grounded("Fee for issuance of amended National Identity card Rs.777.00",
                           far, value="Rs.777.00")


def test_a_postage_row_is_postage_whatever_the_model_called_it():
    q = "Fee for sending National Identity card by registered post under normal service. Rs.120.00"
    p = {"fees": [{"qualifier": "normal", "variant": "lost", "amount_text": "Rs.120.00", "evidence": q}]}
    r = run(FakeLLM(p), text=NIC_PAGE_2, service="svc:nic")
    assert [f.fact_id for f in r.facts if f.predicate == "fee"] == ["svc:nic:fee:lost_postage"]


@pytest.mark.parametrize("wording", [
    "has exceeded 06 months",
    "does not obtain a National Identity card within six months",
    "applies after 6 months",
])
def test_one_late_penalty_has_one_condition_however_it_is_worded(wording):
    assert canonical_condition(wording) == "after_6m"


def test_a_list_returned_where_text_is_expected_is_accepted():
    p = {"processing_times": [{"qualifier": "normal", "text": ["3 days", "within the province"],
                               "evidence": "Normal Basis - 30 working days"}]}
    r = run(FakeLLM(p))
    items = [d for d in r.dropped if "did not match the schema" in d["reason"]]
    assert items == []  # coerced, not rejected for its shape


def test_the_model_reply_is_kept_on_the_result():
    r = run(FakeLLM(good_payload()))
    assert r.raw_reply.startswith("{") and "fees" in r.raw_reply


# ================= second NIC run: empty values, paraphrased eligibility, same amount twice
def test_a_time_with_no_stated_duration_is_dropped_with_an_honest_reason():
    p = {"processing_times": [{"qualifier": "normal", "text": None,
                               "evidence": "Normal Basis - 30 working days"}]}
    r = run(FakeLLM(p))
    assert r.facts == [] or all(f.predicate != "processing_time" for f in r.facts)
    assert "states no value" in r.dropped[0]["reason"]


def test_eligibility_is_stored_as_the_pages_own_sentence_not_the_models_paraphrase():
    sentence = "Every person who is a citizen of Sri Lanka and who has attained the age of 15 years shall apply for a card."
    page = f"Notes\n{sentence} Other text follows here.\n"
    p = {"eligibility": "This service is for citizens aged 15 or over",
         "eligibility_evidence": sentence + " Other text follows here."}
    r = run(FakeLLM(p), text=page)
    elig = next(f for f in r.facts if f.predicate == "eligibility")
    assert elig.value_text == sentence


def test_the_same_amount_in_two_formats_is_one_fact_not_a_conflict():
    quote1, quote2 = "Fee for a lost card. Rs.2500.00", "Fee for a lost card. Rs.2500/-"
    page = f"{quote1}\n{quote2}\n"
    p = {"fees": [fee("standard", None, None, "Rs.2500.00", quote1),
                  fee("standard", None, None, "Rs.2500/-", quote2)]}
    r = run(FakeLLM(p), text=page)
    # "lost" is read from the quote, so the id carries it; the two formats collapse to one fact
    assert [f.fact_id for f in r.facts if f.predicate == "fee"] == ["svc:passport:fee:lost_standard"]
    assert not any("already holds" in d["reason"] for d in r.dropped)


def test_a_different_amount_in_the_same_position_is_still_a_conflict():
    page = "Fee for a lost card. Rs.2500.00\nFee for a lost card. Rs.3000.00\n"
    p = {"fees": [fee("standard", None, None, "Rs.2500.00", "Fee for a lost card. Rs.2500.00"),
                  fee("standard", None, None, "Rs.3000.00", "Fee for a lost card. Rs.3000.00")]}
    r = run(FakeLLM(p), text=page)
    assert any("already holds" in d["reason"] for d in r.dropped)


@pytest.mark.parametrize("reason,token", [
    ("failure to obtain a National Identity Card within the prescribed time limit", "late_application"),
    ("Submission of false information", "false_information"),
    ("Submission of original applications on two occasions", "repeat_submission"),
])
def test_penalty_reasons_become_named_conditions(reason, token):
    assert canonical_condition(reason) == token


def test_a_penalty_fee_gets_a_penalty_id():
    quote = "Submission of false information Rs.2500.00"
    p = {"fees": [{"qualifier": None, "variant": None, "condition": "Submission of false information",
                   "kind": "penalty", "amount_text": "Rs.2500.00", "evidence": quote}]}
    r = run(FakeLLM(p), text=quote + "\n", service="svc:nic")
    assert [f.fact_id for f in r.facts if f.predicate == "fee"] == ["svc:nic:fee:penalty_false_information"]
    assert r.facts[0].detail["kind"] == "penalty"


# ===================================== form links: read from the page, never from the model
FORM_PAGE = r"""
| 1 | Duly completed application [(Form D.R.P/1,7,8)](https://drp.gov.lk/en/assets\formats\application.pdf) |
| 2 | Citizenship certificate [(specimen of a citizenship certificate)](https://drp.gov.lk/en/assets\downloads\citizenship.pdf) |
| 3 | Birth certificate or extract of the birth registry |
"""


def forms_for(quote, name):
    p = {"documents": [{"name": name, "evidence": quote}]}
    r = run(FakeLLM(p), text=FORM_PAGE, service="svc:nic")
    return next(f for f in r.facts if f.predicate == "document")


def test_the_form_link_is_read_from_the_page_beside_the_quote():
    f = forms_for("Duly completed application (Form D.R.P/1,7,8)", "Duly completed application")
    forms = f.detail["forms"]
    assert [x["label"] for x in forms] == ["Form D.R.P/1,7,8"]
    assert forms[0]["url"] == "https://drp.gov.lk/en/assets/formats/application.pdf"  # no backslashes, no //
    assert forms[0]["kind"] == "form"


def test_a_specimen_is_marked_as_such_and_is_not_a_form_to_fill():
    f = forms_for("Citizenship certificate (specimen of a citizenship certificate)",
                  "Citizenship certificate")
    assert f.detail["forms"][0]["kind"] == "specimen"


def test_a_document_with_no_link_on_its_line_has_no_forms():
    f = forms_for("Birth certificate or extract of the birth registry",
                  "Birth certificate or extract of the birth registry")
    assert "forms" not in f.detail


def test_the_model_cannot_invent_a_form_address():
    p = {"documents": [{"name": "Birth certificate", "forms": [{"url": "https://evil.example/x.pdf"}],
                        "evidence": "Birth certificate or extract of the birth registry"}]}
    f = next(x for x in run(FakeLLM(p), text=FORM_PAGE, service="svc:nic").facts
             if x.predicate == "document")
    assert "forms" not in f.detail


@pytest.mark.parametrize("text,value", [
    ("ten thousand rupees", 10_000.0),
    ("two thousand rupees", 2_000.0),
    ("rupees five hundred", 500.0),
    ("Five million rupees", 5_000_000.0),
    ("Five hundred million rupees", 500_000_000.0),
])
def test_a_fee_spelled_out_in_words_still_gives_a_number(text, value):
    from app.core.extraction.ontology import parse_amount

    assert parse_amount(text) == (value, "LKR")


def test_a_year_near_rupees_does_not_get_mistaken_for_the_fee():
    from app.core.extraction.ontology import parse_amount

    assert parse_amount("rupees are the currency of Sri Lanka")[0] is None


def test_tin_certificate_maps_to_the_tin_service():
    from app.core.extraction.vocabulary import canonical_document

    c = canonical_document("TIN Certificate")
    assert c.service_id == "svc:taxpayer_identification_number_tin"


def test_a_directors_passport_is_not_the_applicants_own_prerequisite():
    from app.core.extraction.vocabulary import names_a_third_party

    assert names_a_third_party("Photocopies of valid Passports of Directors")
    assert names_a_third_party("A certified copy of the deceased's birth certificate")
    assert not names_a_third_party("Original passport of the applicant")
    assert not names_a_third_party("Passport")
