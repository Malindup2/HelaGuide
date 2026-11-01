"""Internal 12-intent state -> contract `intent`: one case per row of the table in technicalWorkFlow.md §7."""
import json
from pathlib import Path

import jsonschema
import pytest

from app.core.projection import SERVICE_IDS, project

KG_MAP = Path(__file__).resolve().parents[2] / "research" / "data" / "kg_service_map.json"


def turn(intent, slots=None, language="mixed", confidence=0.9, turn_id=0):
    """A minimal Session.step() result."""
    return {"intent": intent, "slots": slots or {}, "language": language,
            "intent_confidence": confidence, "turn_id": turn_id}


CASES = [
    # internal intent, slots, text, contract intent, service_id
    ("nic_new", {}, "mata aluth ID ekak ganna one", "apply_service", "svc:nic"),
    ("nic_update", {}, "ID eke address eka wenas karanna one", "apply_service", "svc:nic"),
    ("nic_replace_lost", {}, "mata ID eka nathi una", "apply_service", "svc:nic"),
    ("passport_new", {}, "passport ekak ganna one", "apply_service", "svc:passport"),
    ("passport_renew", {}, "passport eka renew karanna one", "apply_service", "svc:passport"),
    ("birth_cert_copy", {}, "uppenna sahathikaye copy ekak one", "apply_service", "svc:birth_certificate"),
    ("marriage_registration", {}, "vivaha lesiyapadinchi karanna one", "apply_service", "svc:marriage_registration"),
    ("death_cert_copy", {}, "marana sahathikaye copy ekak one", "apply_service", "svc:death_certificate"),
    # general_question: requirements wording -> check_requirements, else service_info
    ("general_question", {"service_mentioned": "passport"}, "passport ekata mona documents da one",
     "check_requirements", "svc:passport"),
    ("general_question", {"service_mentioned": "NIC"}, "what do I need for an NIC?", "check_requirements", "svc:nic"),
    ("general_question", {"service_mentioned": "birth certificate"}, "උප්පැන්න සහතිකයට ඕනෙ මොනවද",
     "check_requirements", "svc:birth_certificate"),
    ("general_question", {"service_mentioned": "death certificate"}, "මරණ සහතිකයට ලේඛන මොනවද",
     "check_requirements", "svc:death_certificate"),
    ("general_question", {"service_mentioned": "marriage registration"}, "marriage registration docs?",
     "check_requirements", "svc:marriage_registration"),
    ("general_question", {"service_mentioned": "passport eka"}, "passport office eka kohada", "service_info",
     "svc:passport"),
    ("general_question", {"service_mentioned": "driving license"}, "licence office eka kohada", "service_info", None),
    ("general_question", {}, "office eka kiyata da wahanne", "service_info", None),
    # no contract intent for these
    ("unsupported_service", {"service_mentioned": "driving license"}, "driving licence ekak ganna one", "unknown", None),
    ("feedback_complaint", {"issue": "fee different"}, "fee eka waradi", "unknown", None),
    ("out_of_scope", {}, "ada kalaguna kohomada", "unknown", None),
    ("unknown", {}, "hmm", "unknown", None),
]


@pytest.mark.parametrize("internal, slots, text, expected_intent, expected_service", CASES,
                         ids=[f"{c[0]}-{i}" for i, c in enumerate(CASES)])
def test_projection_row(internal, slots, text, expected_intent, expected_service, intent_schema):
    out = project(turn(internal, slots), "anon-test", text)
    assert out.intent == expected_intent
    assert out.entities.service_id == expected_service
    jsonschema.validate(out.model_dump(mode="json"), intent_schema)


def test_projection_copies_session_fields(intent_schema):
    out = project(turn("nic_replace_lost", {"district": "Galle", "urgency": "urgent"}, language="si",
                       confidence=0.8123, turn_id=3), "anon-xyz", "ne ne, Galle")
    assert out.session_id == "anon-xyz"
    assert out.turn_id == 3
    assert out.language == "si"
    assert out.confidence == 0.8123
    assert out.entities.district == "Galle"
    body = out.model_dump(mode="json")
    assert set(body["entities"]) == {"service_id", "district"}   # other slots stay inside C1
    jsonschema.validate(body, intent_schema)


def test_district_is_null_without_slot(intent_schema):
    out = project(turn("passport_new"), "anon-test", "passport ekak ganna one")
    assert out.entities.district is None
    jsonschema.validate(out.model_dump(mode="json"), intent_schema)


def test_service_ids_match_kg_service_map():
    kg = json.loads(KG_MAP.read_text(encoding="utf-8"))["intents"]
    assert SERVICE_IDS == {intent: row["kg_service_id"] for intent, row in kg.items()}
