"""
Projection of C1's internal 12-intent state onto the team contract (contracts/schema/v1/intent.schema.json).

The contract has 4 intents and only service_id + district as entities, so the rest of the state (variant,
other slots, route) stays inside C1; /v1/intent/details exposes it. Table: research/docs/technicalWorkFlow.md §7.
"""
import re

from helaguide_common.contracts import Intent, IntentEntities

from app.core.dst import SERVICE_OF_INTENT, canon_value

# internal intent -> KG service ID. From research/data/kg_service_map.json (kg_service_id); that file is not in
# the Docker image, so the IDs are copied here and tests/test_projection.py checks the two agree.
SERVICE_IDS = {
    "nic_new": "svc:nic",
    "nic_update": "svc:nic",
    "nic_replace_lost": "svc:nic",
    "passport_new": "svc:passport",
    "passport_renew": "svc:passport",
    "birth_cert_copy": "svc:birth_certificate",
    "marriage_registration": "svc:marriage_registration",
    "death_cert_copy": "svc:death_certificate",
}

# canonical service_mentioned value (dst.SERVICES) -> KG service ID, through the intent that serves it
SERVICE_MENTIONED_IDS = {name: SERVICE_IDS[intent] for intent, name in SERVICE_OF_INTENT.items()}

# a general question that asks what documents are needed -> check_requirements
REQUIREMENTS = re.compile(
    r"\bdocs?\b|\bdocuments?\b|ලේඛන|what do i need|ඕනෙ මොනවද|ඕනේ මොනවද|one monawada",
    re.IGNORECASE,
)


def contract_intent(internal_intent: str, text: str) -> str:
    if internal_intent in SERVICE_IDS:
        return "apply_service"
    if internal_intent == "general_question":
        return "check_requirements" if REQUIREMENTS.search(text or "") else "service_info"
    return "unknown"    # unsupported_service, feedback_complaint, out_of_scope, unknown


def service_id(internal_intent: str, slots: dict) -> str | None:
    if internal_intent in SERVICE_IDS:
        return SERVICE_IDS[internal_intent]
    if internal_intent == "general_question" and slots.get("service_mentioned"):
        return SERVICE_MENTIONED_IDS.get(canon_value("service_mentioned", slots["service_mentioned"]))
    return None


def project(result: dict, session_id: str, text: str) -> Intent:
    """result: one Session.step() output. text: the user's message for this turn."""
    internal = result["intent"]
    return Intent(
        session_id=session_id,
        turn_id=result["turn_id"],
        language=result["language"],
        intent=contract_intent(internal, text),
        entities=IntentEntities(
            service_id=service_id(internal, result["slots"]),
            district=result["slots"].get("district"),
        ),
        confidence=result["intent_confidence"],
    )
