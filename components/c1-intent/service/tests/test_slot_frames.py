"""New slot frame on an intent switch, requested-slot leakage, and the confirmation wording."""
import json
from pathlib import Path

import pytest

from app.core.dst import DialogueStateTracker, SlotExtractor
from app.core.engine import ASK, REPLIES, confirmation

from tests.test_intent_policy import Chat

COMPONENT = Path(__file__).resolve().parents[2]


def test_nic_then_birth_certificate_for_my_daughter(client, real_mode):
    """nic_replace_lost in Galle, urgency no; then "also i need birth certificate"; the bot asks the purpose
    and the citizen answers "for my daughter"."""
    real_mode.update({
        "mage ID eka nathi una": ("nic_replace_lost", 0.9),
        "Galle": ("nic_replace_lost", 0.6),
        "no": ("nic_replace_lost", 0.5),
        "also i need birth certificate": ("nic_replace_lost", 0.6),          # the window still says NIC
        ("current", "also i need birth certificate"): ("birth_cert_copy", 0.9),
        "for my daughter": ("birth_cert_copy", 0.7),
        "yes": ("birth_cert_copy", 0.5),
    })
    chat = Chat(client)
    chat.say("mage ID eka nathi una")
    chat.say("Galle")
    assert chat.reply == ASK["urgency"]["en"]
    d = chat.say("no")
    assert d["slots"] == {"district": "Galle", "urgency": "normal"} and d["ready"] is True

    d = chat.say("also i need birth certificate")
    assert (d["active_intent"], d["intent_source"]) == ("birth_cert_copy", "current_message_switch")
    assert d["slots"] == {"district": "Galle"}          # new frame: no applicant_for (no "self" from "i")
    assert d["assumed_slots"] == ["district"]
    assert d["missing_slots"] == ["applicant_for", "purpose"]
    assert d["completed_requests"][0]["slots"] == {"district": "Galle", "urgency": "normal"}

    d = chat.say("for my daughter", bot_text=ASK["purpose"]["en"])
    assert d["slots"]["applicant_for"] == "child"
    assert "purpose" not in d["slots"]
    assert d["missing_slots"] == ["purpose"]
    assert d["slots"]["district"] == "Galle" and d["assumed_slots"] == ["district"]
    assert d["ready"] is False
    assert d["reply"] == REPLIES["confirm_assumed"]["en"].format(value="Galle")     # "Still in Galle, right?"

    d = chat.say("yes")
    assert d["assumed_slots"] == [] and d["slots"]["district"] == "Galle"
    assert d["reply"] == ASK["purpose"]["en"]
    assert "for for" not in d["reply"]


def test_eyata_carries_applicant_for_but_district_stays_assumed(client, real_mode):
    """birth certificate for the daughter in Galle, then "eyata ID eka ganna one": the new NIC frame keeps
    applicant_for (the pronoun points back to her), while Galle is carried only as an assumption."""
    real_mode.update({
        "duwage birth certificate copy ekak one": ("birth_cert_copy", 0.9),
        "Galle": ("birth_cert_copy", 0.6),
        "school walata": ("birth_cert_copy", 0.6),
        "eyata ID eka ganna one": ("nic_new", 0.9),
    })
    chat = Chat(client)
    chat.say("duwage birth certificate copy ekak one")
    chat.say("Galle")
    assert chat.say("school walata")["ready"] is True

    d = chat.say("eyata ID eka ganna one")
    assert (d["active_intent"], d["intent_source"]) == ("nic_new", "current_message_switch")
    assert d["slots"] == {"applicant_for": "child", "district": "Galle"}
    assert d["assumed_slots"] == ["district"]
    assert d["missing_slots"] == ["date_of_birth"]
    assert d["reply"] == REPLIES["confirm_assumed"]["en"].format(value="Galle")


def test_no_to_the_assumed_district_asks_again(client, real_mode):
    real_mode.update({
        "mage ID eka nathi una": ("nic_replace_lost", 0.9),
        "Galle": ("nic_replace_lost", 0.6),
        "no": ("nic_replace_lost", 0.5),
        "uppenna sahathikayak one, duwata": ("birth_cert_copy", 0.9),
        "na": ("birth_cert_copy", 0.5),
    })
    chat = Chat(client)
    for text in ("mage ID eka nathi una", "Galle", "no"):
        chat.say(text)
    d = chat.say("uppenna sahathikayak one, duwata")
    assert d["reply"] == REPLIES["confirm_assumed"]["en"].format(value="Galle")
    d = chat.say("na")
    assert "district" not in d["slots"] and d["assumed_slots"] == []
    assert d["reply"] == ASK["district"]["en"]


# ---------------------------------------------------------------- tracker and extractor (research copy = service copy)
def test_tracker_switch_starts_a_new_frame():
    t = DialogueStateTracker(SlotExtractor())
    t.update("mata aluth ID ekak one, mama Galle inne", "nic_new")
    assert t.slots == {"applicant_for": "self", "district": "Galle"}
    t.update("uppenna sahathikayak one", "birth_cert_copy")
    assert t.slots == {"district": "Galle"} and t.assumed == {"district"}
    t.update("Galle thama", "birth_cert_copy")
    assert t.assumed == set()
    t.update("passport ekak one", "passport_new")       # passport has no district slot
    assert t.slots == {}


def _gold_dialogue(file_name, dialogue_id):
    data = json.loads((COMPONENT / "research" / "data" / file_name).read_text(encoding="utf-8"))
    return next(d for d in data if d["dialogue_id"] == dialogue_id)


@pytest.mark.parametrize("file_name, dialogue_id", [
    ("seed_dialogues_v1.json", "d046"),             # "eyata ID eka ganna" after the daughter's birth certificate
    ("seed_dialogues_v2_pure_si.json", "d069"),     # "එයාට හැඳුනුම්පත ගන්න" after the son's birth certificate
])
def test_tracker_back_reference_carries_applicant_for(file_name, dialogue_id):
    """Gold intent-switch dialogues: the pronoun carries applicant_for into the new NIC frame."""
    t = DialogueStateTracker(SlotExtractor())
    bot_text = None
    for turn in _gold_dialogue(file_name, dialogue_id)["turns"]:
        if turn["speaker"] == "bot":
            bot_text = turn["text"]
            continue
        state = t.update(turn["text"], turn["state"]["intent"], bot_text)
        assert state["slots"] == turn["state"]["slots"], turn["text"]
    assert t.intent == "nic_new" and t.slots == {"applicant_for": "child"}


def test_tracker_switch_without_back_reference_drops_applicant_for():
    t = DialogueStateTracker(SlotExtractor())
    t.update("duwage birth certificate copy ekak one, Galle", "birth_cert_copy")
    assert t.slots == {"applicant_for": "child", "district": "Galle"}
    t.update("ID eka ganna one", "nic_new", bot_text="Mokatada one?")
    assert t.slots == {"district": "Galle"} and t.assumed == {"district"}


def test_requested_slot_does_not_take_another_slots_answer():
    x = SlotExtractor()
    out = x.extract("for my daughter", "birth_cert_copy", bot_text="Mokatada one?")
    assert out["applicant_for"]["value"] == "child" and "purpose" not in out


def test_purpose_only_from_the_keyword_list():
    x = SlotExtractor()
    assert "purpose" not in x.extract("mage wada walata", "death_cert_copy", bot_text="Mokatada one?")
    assert x.extract("pension ekata", "death_cert_copy", bot_text="Mokatada one?")["purpose"]["value"] == "pension"
    assert x.extract("foreign employment walata", "birth_cert_copy")["purpose"]["value"] == "foreign employment"


def test_new_value_free_text_still_works():
    x = SlotExtractor()
    out = x.extract("No 12, Main Street, Kandy", "nic_update", bot_text="Aluth address eka mokakda?")
    assert out["new_value"]["value"] == "No 12, Main Street, Kandy"


def test_bare_subject_pronoun_is_not_self():
    x = SlotExtractor()
    assert "applicant_for" not in x.extract("also i need birth certificate", "birth_cert_copy")
    assert "applicant_for" not in x.extract("mama passport ekak ganna one", "passport_new")
    assert x.extract("mata passport ekak ganna one", "passport_new")["applicant_for"]["value"] == "self"


def test_confirmation_does_not_double_for():
    slots = {"applicant_for": "child", "district": "Galle", "purpose": "for school"}
    text = confirmation("birth_cert_copy", slots, "en")
    assert "for for" not in text and "for school" in text


def test_research_and_service_dst_are_in_sync():
    """service/app/core/dst.py = research/experiments/c1_dst.py plus a 2-line header."""
    research = (COMPONENT / "research" / "experiments" / "c1_dst.py").read_text(encoding="utf-8").splitlines()
    service = (COMPONENT / "service" / "app" / "core" / "dst.py").read_text(encoding="utf-8").splitlines()
    assert service[2:] == research
