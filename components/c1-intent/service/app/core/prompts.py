"""
Prompts for the LLM dialogue layer. The services, slots and allowed values are generated from the tracker's own
tables (dst.INTENT_SLOTS, the validator's enums, dst.PURPOSES ...), never written out by hand, so the prompt and
the validator cannot drift apart.

    system_prompt(today)                         -> the instructions + the service catalogue + the JSON format
    turn_message(state, message, hints=None)     -> the user content for this turn (hints=None in llm-only mode)
"""
import json
from datetime import date, datetime, timedelta, timezone

from app.core.dst import DISTRICTS, INTENT_SLOTS, ISSUES, PURPOSES
from app.core.engine import CORE_INTENTS, SERVICE_NAMES
from app.core.validator import DIALOGUE_ACTS, ENUMS, OTHER

# Sri Lanka has no daylight saving: a fixed offset needs no tz database (zoneinfo has none on Windows)
COLOMBO = timezone(timedelta(hours=5, minutes=30), "Asia/Colombo")

OTHER_INTENTS = {
    "unsupported_service": "a government service HelaGuide does not cover (driving licence, police clearance, "
                           "business registration, building permit, utility connection, residence certificate ...)",
    "general_question": "a question about one of the supported services (documents, fees, offices, timing)",
    "feedback_complaint": "a complaint about a service or about earlier advice",
    "out_of_scope": "anything that is not about government services",
}
SLOT_HELP = {
    "applicant_for": "who the document is for",
    "district": "the district (one of the 25 below); a town is fine, give its district",
    "date_of_birth": "the applicant's date of birth",
    "change_field": "what to change on the NIC",
    "new_value": "the new name or address, in the user's words",
    "urgency": "whether it is needed urgently",
    "service_type": "normal or one-day (urgent) passport service",
    "travel_date": "when the user travels",
    "purpose": "what the certificate is needed for",
    "date": "the marriage date",
    "service_mentioned": "which service the user is talking about",
    "issue": "what went wrong",
}
REPLY_LANGUAGE = {"en": "English", "si": "Sinhala in Sinhala script",
                  "mixed": "Singlish: romanized Sinhala mixed with English, the way the user writes"}


def today_colombo() -> date:
    return datetime.now(COLOMBO).date()


def _values(slot):
    if slot in ENUMS:
        return " | ".join(canon for canon, _ in ENUMS[slot])
    if slot == "purpose":
        return " | ".join(c for c, _ in PURPOSES) + f" | {OTHER} (then the user's words)"
    if slot == "issue":
        return " | ".join(c for c, _ in ISSUES) + f" | {OTHER} (then the user's words)"
    if slot in ("date", "travel_date", "date_of_birth"):
        return "YYYY-MM-DD"
    return None


def _catalogue():
    lines = ["Supported services (internal intent: what it is; required slots in the order to ask them):"]
    for intent in INTENT_SLOTS:
        if intent in CORE_INTENTS:
            lines.append(f"- {intent}: {SERVICE_NAMES[intent][0]}; slots: {', '.join(INTENT_SLOTS[intent])}")
    lines.append("Other intents:")
    for intent, what in OTHER_INTENTS.items():
        slots = INTENT_SLOTS[intent]
        lines.append(f"- {intent}: {what}" + (f"; slots: {', '.join(slots)}" if slots else ""))
    lines.append("Slots and their values:")
    for slot, what in SLOT_HELP.items():
        values = _values(slot)
        lines.append(f"- {slot}: {what}" + (f". Values: {values}" if values else ""))
    lines.append("Districts: " + ", ".join(DISTRICTS))
    return "\n".join(lines)


def system_prompt(today: date | None = None) -> str:
    today = today or today_colombo()
    return f"""You are HelaGuide, a friendly assistant that helps Sri Lankan citizens with government services.
Today is {today.isoformat()} ({today.strftime("%A")}) in Sri Lanka.

{_catalogue()}

How to talk:
- Reply in the language given as reply_language in the user content ({"; ".join(f"{k} = {v}" for k, v in REPLY_LANGUAGE.items())}). Keep replies short and natural.
- Pick up slots whenever the user mentions them, in any order, several at once. Never ask again for a slot that is already filled.
- Ask for at most one missing slot per reply, in the order listed for the service, conversationally.
- If the user starts a new request, handle it and keep the unfinished one in tasks.
- unsupported_service (for example a driving licence): say politely that HelaGuide does not cover it yet, and offer to continue the open task if there is one.
- Greetings and small talk with no service info get a natural reply; if they contain info, still extract it. With no request yet, active_intent is null.
- When every required slot of the active service is filled, summarise them and ask the user to confirm (ready_to_confirm = true). Never set ready_to_confirm while a slot is missing.
- Change a filled slot only when the user corrects it (dialogue_act = correction).
- If the user does not know a value, set that slot to "unknown".

Slot values:
- Use only the values listed above for slots that have them. Districts by their English name.
- Dates are ISO YYYY-MM-DD. Resolve relative dates yourself from today's date ("next friday", "ලබන මාසේ", "mid December" = the 15th).
- slot_updates holds only the slots this message gives or changes, for active_intent. Leave everything else out.

Return only this JSON object, no other text:
{{"reply": "...", "dialogue_act": "{'|'.join(DIALOGUE_ACTS)}",
  "active_intent": "<one of the intents above, or null>", "tasks": ["<unfinished service intents>"],
  "slot_updates": {{"slot": "value"}}, "asks_slot": "<the slot your reply asks for, or null>",
  "ready_to_confirm": false}}"""


def turn_message(state: dict, message: str, hints: dict | None = None) -> str:
    """The user content for one turn: the current state, the NLU hints (hybrid mode only) and the new message."""
    content = {"state": state}
    if hints is not None:
        content["nlu_hints"] = hints
    content["message"] = message
    return json.dumps(content, ensure_ascii=False, indent=1)
