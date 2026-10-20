"""Condition facts (applicant_age / applicant_minor), family keywords for applicant_for, and the variant question
for a bare service mention ("i need a NIC")."""
import pytest

from app.core.dst import DialogueStateTracker, SlotExtractor, extract_conditions
from app.core.engine import ASK, REPLIES, VARIANT_QUESTIONS

from tests.test_intent_policy import Chat


def test_nic_then_passport_for_younger_sister(client, real_mode):
    """hi -> "i need a NIC" (which NIC?) -> new NIC for me in Galle -> "also i need the information for passport"
    (new or renewal?) -> "nangita" -> normal -> next year -> "she is 14 years still"."""
    passport = "also i need the information for passport"
    real_mode.update({
        "i need a NIC": ("nic_replace_lost", 0.8),          # the classifier's guess for a bare mention
        "aluth ekak": ("nic_replace_lost", 0.6),
        "mata": ("nic_new", 0.6),
        "Galle": ("nic_new", 0.6),
        passport: ("nic_new", 0.7),                         # the window still says NIC
        ("current", passport): ("passport_new", 0.8),
        "nangita": ("passport_new", 0.6),
        "normal": ("passport_new", 0.6),
        "next year": ("passport_new", 0.6),
        "she is 14 years still": ("passport_new", 0.6),
    })
    chat = Chat(client)
    d = chat.say("hi")
    assert d["reply"] == REPLIES["greeting"]["en"] and d["state_version"] == 0

    d = chat.say("i need a NIC")
    assert d["variant_pending"] is True and d["ready"] is False
    assert d["reply"] == VARIANT_QUESTIONS["svc:nic"]["en"]
    assert d["intent"]["entities"]["service_id"] == "svc:nic"        # the service is known, only the variant is not
    assert d["state_version"] == 1

    d = chat.say("aluth ekak")
    assert (d["active_intent"], d["intent_source"], d["variant_pending"]) == ("nic_new", "variant_answer", False)
    assert d["reply"] == ASK["applicant_for"]["en"]
    chat.say("mata")
    d = chat.say("Galle")
    assert d["slots"] == {"applicant_for": "self", "district": "Galle"}
    assert d["reply"] == ASK["date_of_birth"]["en"]

    d = chat.say(passport)
    assert (d["active_intent"], d["intent_source"]) == ("passport_new", "current_message_switch")
    assert d["variant_pending"] is True and d["reply"] == VARIANT_QUESTIONS["svc:passport"]["en"]
    assert [r["intent"] for r in d["pending_requests"]] == ["nic_new"]

    d = chat.say("nangita")
    assert (d["active_intent"], d["intent_source"], d["variant_pending"]) == ("passport_new", "variant_answer", False)
    assert d["slots"]["applicant_for"] == "other"
    assert d["reply"] == ASK["service_type"]["en"]
    chat.say("normal")
    d = chat.say("next year")
    assert d["ready"] is True
    slots, version = d["slots"], d["state_version"]
    assert slots == {"applicant_for": "other", "service_type": "normal", "travel_date": "next year", "district": "Galle"}
    assert d["conditions"] == {}

    d = chat.say("she is 14 years still")
    assert d["conditions"] == {"applicant_age": 14, "applicant_minor": True}
    assert d["slots"] == slots and d["active_intent"] == "passport_new" and d["ready"] is True
    assert d["state_version"] == version + 1
    assert set(d["intent"]["entities"]) == {"service_id", "district"}       # the /v1/intent projection is unchanged

    d = chat.say("hi")
    assert d["state_version"] == version + 1 and d["conditions"] == {"applicant_age": 14, "applicant_minor": True}


# ---------------------------------------------------------------- bare service mentions
@pytest.mark.parametrize("text, guess, service", [
    ("i need a NIC", ("nic_replace_lost", 0.8), "svc:nic"),
    ("NIC ekak one", ("nic_update", 0.7), "svc:nic"),
    ("passport ekak one", ("passport_renew", 0.7), "svc:passport"),
    ("i need a passport", ("passport_new", 0.9), "svc:passport"),
])
def test_bare_service_mention_asks_the_variant(client, real_mode, text, guess, service):
    real_mode[text] = guess
    d = Chat(client).say(text)
    assert d["variant_pending"] is True and d["ready"] is False
    assert d["reply"] == VARIANT_QUESTIONS[service]["en"]


def test_unsure_bare_mention_still_keeps_the_service(client, real_mode):
    real_mode["NIC ekak one"] = ("out_of_scope", 0.2)
    d = Chat(client).say("NIC ekak one")
    assert (d["active_intent"], d["intent_source"], d["variant_pending"]) == ("nic_new", "service_keyword", True)
    assert d["reply"] == VARIANT_QUESTIONS["svc:nic"]["en"]


@pytest.mark.parametrize("text, intent, next_question", [
    ("nic eka nathi una", "nic_replace_lost", "district"),
    ("mage ID eka nathi una", "nic_replace_lost", "district"),
    ("NIC eke address eka wenas karanna one", "nic_update", "new_value"),
    ("passport eka renew karanna one", "passport_renew", "service_type"),
    ("passport ekak ganna one", "passport_new", "applicant_for"),
])
def test_a_variant_cue_goes_straight_to_the_request(client, real_mode, text, intent, next_question):
    real_mode[text] = (intent, 0.9)
    d = Chat(client).say(text)
    assert (d["active_intent"], d["variant_pending"]) == (intent, False)
    assert d["reply"] == ASK[next_question]["en"]


def test_variant_answer_keeps_the_slots_said_before(client, real_mode):
    real_mode.update({"NIC ekak one, mama Galle inne": ("nic_new", 0.8), "nathi una": ("nic_new", 0.6)})
    chat = Chat(client)
    assert chat.say("NIC ekak one, mama Galle inne")["slots"] == {"district": "Galle"}
    d = chat.say("nathi una")
    assert (d["active_intent"], d["intent_source"]) == ("nic_replace_lost", "variant_answer")
    assert d["slots"] == {"district": "Galle"} and d["missing_slots"] == ["urgency"]


def test_answer_without_a_cue_asks_again(client, real_mode):
    real_mode.update({"i need a NIC": ("nic_new", 0.8), "Galle": ("nic_update", 0.7)})
    chat = Chat(client)
    chat.say("i need a NIC")
    d = chat.say("Galle")
    assert (d["active_intent"], d["variant_pending"]) == ("nic_new", True)     # district: every NIC variant has it
    assert d["slots"] == {"district": "Galle"}
    assert d["reply"] == VARIANT_QUESTIONS["svc:nic"]["en"]


# ---------------------------------------------------------------- condition facts
@pytest.mark.parametrize("text, age", [
    ("she is 14 years still", 14), ("14 years", 14), ("14 yrs", 14), ("she is 14", 14), ("avurudu 14", 14),
    ("awurudu 14", 14), ("අවුරුදු 14", 14), ("mata wayasa 14i", 14), ("he is 25", 25),
])
def test_age_forms(text, age):
    assert extract_conditions(text) == {"applicant_age": age, "applicant_minor": age < 18}


@pytest.mark.parametrize("text", ["under 18", "she is a minor", "eya minor"])
def test_minor_without_an_age(text):
    assert extract_conditions(text) == {"applicant_minor": True}


@pytest.mark.parametrize("text", [
    "No. 14, Temple Road", "2010-05-14", "14/05/2010", "Colombo 7", "2010 may 14", "ID eka nathi wela avurudu 2 kalin",
    "lost it 2 years ago", "valid for 10 years", "my number is 14", "minor correction in the name",
])
def test_not_an_age(text):
    assert extract_conditions(text) == {}


def test_address_answer_is_not_an_age():
    t = DialogueStateTracker(SlotExtractor())
    t.update("NIC eke address eka wenas karanna one", "nic_update")
    state = t.update("No. 14, Temple Road", "nic_update", bot_text="Aluth address eka mokakda?")
    assert state["slots"]["new_value"] == "No. 14, Temple Road" and state["conditions"] == {}


def test_conditions_carry_only_with_a_back_reference():
    t = DialogueStateTracker(SlotExtractor())
    t.update("nangita passport ekak ganna one, she is 14", "passport_new")
    assert t.conditions == {"applicant_age": 14, "applicant_minor": True}
    t.update("eyata ID ekak ganna one", "nic_new")
    assert t.slots == {"applicant_for": "other"} and t.conditions == {"applicant_age": 14, "applicant_minor": True}

    t = DialogueStateTracker(SlotExtractor())
    t.update("nangita passport ekak ganna one, she is 14", "passport_new")
    t.update("ID ekak ganna one", "nic_new")
    assert t.slots == {} and t.conditions == {}


def test_minor_drops_an_adult_age():
    t = DialogueStateTracker(SlotExtractor())
    t.update("he is 19", "passport_new")
    t.update("sorry, he is a minor", "passport_new")
    assert t.conditions == {"applicant_minor": True}


# ---------------------------------------------------------------- family keywords
@pytest.mark.parametrize("word, value", [
    ("nangita", "other"), ("nangige", "other"), ("mallita", "other"), ("malliita", "other"), ("malliage", "other"),
    ("akkata", "other"), ("akkage", "other"), ("ayyata", "other"), ("ayyage", "other"),
    ("නංගිට", "other"), ("මල්ලිට", "other"), ("අක්කට", "other"), ("අයියට", "other"), ("අයියගේ", "other"),
    ("අම්මට", "parent"), ("තාත්තට", "parent"), ("අම්මාට", "parent"),
])
def test_family_words_fill_applicant_for(word, value):
    assert SlotExtractor().extract(word, "passport_new")["applicant_for"]["value"] == value


def test_for_her_still_carries_the_sibling():
    t = DialogueStateTracker(SlotExtractor())
    t.update("nangige birth certificate eka one", "birth_cert_copy")
    t.update("i need an NIC for her", "nic_new")
    assert t.slots == {"applicant_for": "other"}
