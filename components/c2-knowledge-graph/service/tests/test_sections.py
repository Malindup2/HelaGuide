"""One page, several services: sections mode. The real-page test uses the saved DRP page."""

import json
import uuid
from pathlib import Path

import pytest

from app.core.acquisition.discover import strip_menus
from app.core.extraction.extractor import build_section_facts, count_headings, extract_sections
from app.core.extraction.llm import LLMReply

REPO_ROOT = Path(__file__).resolve().parents[4]
REAL = REPO_ROOT / "components/c2-knowledge-graph/research/data/crawl/archive/2026-10-11/91b335930fed6de6.md"
URL = "https://drp.gov.lk/en/other_service.php"
WHEN = "2026-10-11T10:00:00+00:00"


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload

    def complete(self, system, user):
        return LLMReply(json.dumps(self.payload), 4000, 3000, "fake-model")


def block(title, slug, is_service=True, **lists):
    return {"title": title, "slug": slug, "is_service": is_service, **lists}


PAGE = """
**Translation of National Identity cards into English**
Receipt obtained by paying Rs.2000/- to the cashier counter for translation of the National Identity card into English.

**Mobile Services**
This opportunity is provided by the Department when a special request is made by any institution.

**Verification of National Identity Card Numbers**
A fee of Rs. 500/- should be paid to the government for confirmation of the National Identity card number of a deceased person.
"""


def test_each_heading_becomes_its_own_service_and_non_services_are_not_staged():
    reply = {"services": [
        block("Translation of National Identity cards into English", "nic_translation",
              fees=[{"qualifier": "standard", "amount_text": "Rs.2000/-",
                     "evidence": "paying Rs.2000/- to the cashier counter for translation of the National Identity card into English"}]),
        block("Mobile Services", "mobile_services", is_service=False),
        block("Verification of National Identity Card Numbers", "nic_number_verification",
              fees=[{"qualifier": "deceased", "amount_text": "Rs. 500/-",
                     "evidence": "A fee of Rs. 500/- should be paid to the government for confirmation of the National Identity card number of a deceased person."}]),
    ]}
    facts, dropped, sections = build_section_facts(reply, strip_menus(PAGE), URL, WHEN)
    ids = {f.fact_id for f in facts}
    assert "svc:nic_translation:fee:standard" in ids
    assert any(i.startswith("svc:nic_number_verification:fee:") for i in ids)
    assert not any(i.startswith("svc:mobile_services") for i in ids)
    assert [s["service_id"] for s in sections] == [
        "svc:nic_translation", "svc:mobile_services", "svc:nic_number_verification"]
    assert dropped == []


def test_a_fact_is_still_dropped_if_the_page_does_not_say_it():
    reply = {"services": [block("Translation", "nic_translation",
                                fees=[{"qualifier": "standard", "amount_text": "Rs.9999/-",
                                       "evidence": "paying Rs.9999/- to the cashier counter"}])]}
    facts, dropped, _ = build_section_facts(reply, strip_menus(PAGE), URL, WHEN)
    assert facts == [] and dropped and "not on the page" in dropped[0]["reason"]


def test_two_sections_with_the_same_slug_do_not_merge():
    reply = {"services": [block("A", "nic_service"), block("B", "nic_service")]}
    _, _, sections = build_section_facts(reply, "text", URL, WHEN)
    assert [s["service_id"] for s in sections] == ["svc:nic_service", "svc:nic_service_2"]


def test_a_reply_without_a_services_list_is_an_error():
    with pytest.raises(ValueError):
        build_section_facts({"fees": []}, "text", URL, WHEN)


def test_extract_sections_keeps_the_reply_and_marks_the_model():
    reply = {"services": [block("Translation", "nic_translation")]}
    r = extract_sections(PAGE, service_id="svc:nic", agency="DRP", source_url=URL,
                         retrieved_at=WHEN, llm=FakeLLM(reply))
    assert r.error == "" and r.model.endswith("[sections]") and '"services"' in r.raw_reply


# ------------------------------------------------------------------ the real saved page
@pytest.mark.skipif(not REAL.exists(), reason="the saved DRP page is not on this machine")
def test_the_real_page_has_several_headed_parts():
    assert count_headings(REAL.read_text(encoding="utf-8")) >= 5


@pytest.mark.skipif(not REAL.exists(), reason="the saved DRP page is not on this machine")
def test_real_quotes_from_each_section_are_grounded_and_forms_follow_their_service():
    """A reply written by hand from lines of the real page, standing in for the model."""
    text = REAL.read_text(encoding="utf-8")
    reply = {"services": [
        block("Translation of National Identity cards into English", "nic_translation",
              fees=[{"qualifier": "standard", "amount_text": "Rs.2000/-",
                     "evidence": "Receipt obtained by paying Rs.2000/- to the cashier counter of the head office of the Department for Registration of Persons for translation of the National Identity card into English."}],
              documents=[{"name": "The form in which the information of the National Identity card is recorded",
                          "evidence": "The form in which the information of the National Identity card is recorded."}]),
        block("Verification of National Identity Card Numbers", "nic_number_verification",
              fees=[{"qualifier": "deceased", "amount_text": "Rs. 500/-",
                     "evidence": "A fee of Rs. 500/- should be paid to the government for confirmation of the National Identity card number of a deceased person."}],
              documents=[{"name": "Birth Certificate", "evidence": "Birth Certificate"}]),
        block("Receiving National Identity cards of deceased persons", "nic_deceased_card_handover",
              documents=[{"name": "Certified photocopy of death certificate",
                          "evidence": "Certified photocopy of death certificate"},
                         {"name": "forms of D.R.P./OP/01/3",
                          "evidence": "03 completed forms of D.R.P./OP/01/3"}]),
    ]}
    facts, dropped, sections = build_section_facts(reply, strip_menus(text), URL, WHEN)
    by_service = {}
    for f in facts:
        by_service.setdefault(f.service_id, []).append(f)
    assert set(by_service) == {"svc:nic_translation", "svc:nic_number_verification",
                               "svc:nic_deceased_card_handover"}
    assert not [d for d in dropped if "not on the page" in d["reason"]], dropped
    # the form on the deceased-card line comes from the page, and belongs to that service
    forms = [x for f in by_service["svc:nic_deceased_card_handover"]
             for x in f.detail.get("forms", [])]
    assert any(x["url"].endswith("Annexure.pdf") for x in forms)
    # The page asks for a certified death certificate. That is another agency's service, but the
    # vocabulary does not yet say which service id it is, so NO link may be invented for it.
    # (A decision to make: map "death certificate" to a service id once RGD's page is in.)
    deceased = by_service["svc:nic_deceased_card_handover"]
    assert any(f.fact_id.endswith("document:death_certificate") for f in deceased)
    assert not any(f.predicate == "prerequisite" and f.detail.get("requires_service") for f in deceased)


def test_a_heading_with_only_an_agency_is_not_staged_as_a_service():
    reply = {"services": [
        block("Translation of National Identity cards into English", "nic_translation",
              agency="Department for Registration of Persons",
              agency_evidence="Translation of National Identity cards into English",
              fees=[{"qualifier": "standard", "amount_text": "Rs.2000/-",
                     "evidence": "paying Rs.2000/- to the cashier counter for translation of the National Identity card into English"}]),
        block("Verification of National Identity Card Numbers", "label_only",
              agency="Department for Registration of Persons",
              agency_evidence="Verification of National Identity Card Numbers"),
    ]}
    facts, _, sections = build_section_facts(reply, strip_menus(PAGE), URL, WHEN)
    assert not any(f.service_id == "svc:label_only" for f in facts)
    shell = next(s for s in sections if s["service_id"] == "svc:label_only")
    assert shell["facts"] == 0 and "not staged" in shell["note"]
    assert any(f.service_id == "svc:nic_translation" for f in facts)


def test_known_services_are_given_to_the_model():
    seen = {}

    class Spy(FakeLLM):
        def complete(self, system, user):
            seen["user"] = user
            return super().complete(system, user)

    extract_sections(PAGE, service_id="svc:nic", agency="DRP", source_url=URL, retrieved_at=WHEN,
                     llm=Spy({"services": []}), known_services=("svc:nic", "svc:passport"))
    assert "svc:nic, svc:passport" in seen["user"]
    assert "exact id" in seen["user"]


def test_two_parts_about_a_known_service_join_it_instead_of_getting_a_suffix():
    reply = {"services": [
        block("Translation of National Identity cards into English", "svc:nic_translation",
              fees=[{"qualifier": "standard", "amount_text": "Rs.2000/-",
                     "evidence": "paying Rs.2000/- to the cashier counter for translation of the National Identity card into English"}]),
        block("Verification of National Identity Card Numbers", "svc:nic_translation",
              fees=[{"qualifier": "deceased", "amount_text": "Rs. 500/-",
                     "evidence": "A fee of Rs. 500/- should be paid to the government for confirmation of the National Identity card number of a deceased person."}]),
    ]}
    known = frozenset({"svc:nic_translation"})
    _, _, with_known = build_section_facts(reply, strip_menus(PAGE), URL, WHEN, known)
    assert {s["service_id"] for s in with_known} == {"svc:nic_translation"}
    _, _, without = build_section_facts(reply, strip_menus(PAGE), URL, WHEN)
    assert {s["service_id"] for s in without} == {"svc:nic_translation", "svc:nic_translation_2"}
