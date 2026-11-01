"""Several requests in one conversation, towns -> districts, "don't know" answers, greetings and warmup.

Uses the fake engine (tests/conftest.py); `real_mode[("current", text)]` sets the current-message-only prediction.
The fake engine tags every Latin-script word EN, so replies come in English here.
"""
from app.core import pipeline
from app.core.engine import ASK, REPLIES

from tests.test_intent_policy import Chat


def nic_lost_in_badulla(real_mode, chat, urgent=True):
    real_mode.update({
        "mage ID eka nathi una": ("nic_replace_lost", 0.9),
        "Badulla": ("nic_replace_lost", 0.6),
        "ikmanata one": ("nic_replace_lost", 0.7),
    })
    chat.say("mage ID eka nathi una")
    d = chat.say("Badulla")
    if urgent:
        d = chat.say("ikmanata one")
    return d


def test_ready_request_is_completed_when_a_new_service_is_named(client, real_mode, intent_schema):
    chat = Chat(client)
    assert nic_lost_in_badulla(real_mode, chat)["ready"] is True
    text = "passport ekakuth ganna one"
    real_mode[text] = ("nic_replace_lost", 0.8)                 # the 3-message window still says NIC
    real_mode[("current", text)] = ("passport_new", 0.7)        # the message alone says passport
    d = chat.say(text)
    assert (d["active_intent"], d["intent_source"]) == ("passport_new", "current_message_switch")
    assert d["completed_requests"] == [{"intent": "nic_replace_lost", "service_id": "svc:nic",
                                        "slots": {"district": "Badulla", "urgency": "urgent"},
                                        "conditions": {}, "variant_pending": False}]
    assert d["pending_requests"] == []
    assert d["slots"]["district"] == "Badulla"                  # carried, though passport does not ask for it
    assert d["missing_slots"] == ["applicant_for", "service_type", "travel_date"]
    assert d["intent"]["entities"] == {"service_id": "svc:passport", "district": "Badulla"}


def test_unfinished_request_is_pending_and_offered_back(client, real_mode):
    chat = Chat(client)
    nic_lost_in_badulla(real_mode, chat, urgent=False)          # urgency still missing
    real_mode.update({
        "passport ekakuth one": ("nic_replace_lost", 0.8),
        ("current", "passport ekakuth one"): ("passport_new", 0.8),
        "mata": ("passport_new", 0.6),
        "normal": ("passport_new", 0.6),
        "next year": ("passport_new", 0.6),
        "ow": ("passport_new", 0.5),
    })
    d = chat.say("passport ekakuth one")
    assert d["active_intent"] == "passport_new"
    assert [r["intent"] for r in d["pending_requests"]] == ["nic_replace_lost"]
    chat.say("mata")
    chat.say("normal")
    d = chat.say("next year")
    assert d["ready"] is True
    assert d["reply"].endswith(REPLIES["offer_pending"]["en"].format(service="NIC"))
    d = chat.say("ow")
    assert (d["active_intent"], d["intent_source"]) == ("nic_replace_lost", "pending_resume")
    assert d["slots"] == {"district": "Badulla"}
    assert d["reply"] == ASK["urgency"]["en"]
    assert [r["intent"] for r in d["completed_requests"]] == ["passport_new"]
    assert d["pending_requests"] == []


def test_message_naming_another_service_switches_even_on_a_slot_answer(client, real_mode):
    chat = Chat(client)
    real_mode["mage ID eka nathi una"] = ("nic_replace_lost", 0.9)
    chat.say("mage ID eka nathi una")                           # asks for the district
    real_mode["passport ekakuth one"] = ("nic_replace_lost", 0.9)
    real_mode[("current", "passport ekakuth one")] = ("passport_new", 0.55)
    assert chat.say("passport ekakuth one")["active_intent"] == "passport_new"


def test_current_message_needs_the_keyword(client, real_mode):
    chat = Chat(client)
    real_mode["mage ID eka nathi una"] = ("nic_replace_lost", 0.9)
    chat.say("mage ID eka nathi una")
    real_mode[("current", "Badulla")] = ("passport_new", 0.9)   # no passport keyword in the message
    assert chat.say("Badulla")["active_intent"] == "nic_replace_lost"


def test_complaint_found_on_the_current_message(client, real_mode):
    chat = Chat(client)
    real_mode["mage ID eka nathi una"] = ("nic_replace_lost", 0.9)
    chat.say("mage ID eka nathi una", bot_text=None)
    text = "office eka wahala thibbe"
    real_mode[text] = ("nic_replace_lost", 0.8)                 # the window pulls it to NIC
    real_mode[("current", text)] = ("feedback_complaint", 0.6)
    d = chat.say(text, bot_text=None)
    assert (d["internal_intent"], d["route"], d["active_intent"]) == \
        ("feedback_complaint", "trust_verification", "nic_replace_lost")


def test_complaint_while_a_slot_question_is_pending(client, real_mode):
    chat = Chat(client)
    real_mode["passport ekak ganna one"] = ("passport_new", 0.8)
    real_mode["normal"] = ("passport_new", 0.7)
    chat.say("passport ekak ganna one")
    chat.say("mata")
    chat.say("normal")                                          # bot asks for the travel date
    text = "oya kiwwa office eka saturday open kiyala, mama giyama wahala thibbe"
    real_mode[text] = ("passport_new", 0.77)                    # what run_v2_seed1 says with the window
    real_mode[("current", text)] = ("feedback_complaint", 0.435)    # and on the message alone
    d = chat.say(text)
    assert (d["internal_intent"], d["route"], d["active_intent"]) ==         ("feedback_complaint", "trust_verification", "passport_new")
    assert d["reply"].endswith(ASK["travel_date"]["en"])


def test_town_fills_district(client, real_mode):
    chat = Chat(client)
    real_mode["mage ID eka nathi una"] = ("nic_replace_lost", 0.9)
    real_mode["mama inne wennappuwe"] = ("nic_replace_lost", 0.6)
    chat.say("mage ID eka nathi una")
    d = chat.say("mama inne wennappuwe")
    assert (d["slots"]["district"], d["slots"]["town"]) == ("Puttalam", "Wennappuwa")
    assert d["intent"]["entities"]["district"] == "Puttalam"
    assert d["reply"] == ASK["urgency"]["en"]


def test_sinhala_script_town_and_correction(client, real_mode):
    chat = Chat(client)
    real_mode["mage ID eka nathi una"] = ("nic_replace_lost", 0.9)
    real_mode["මීගමුවේ"] = ("nic_replace_lost", 0.6)
    real_mode["ne ne, Galle"] = ("nic_replace_lost", 0.6)
    chat.say("mage ID eka nathi una")
    d = chat.say("මීගමුවේ")
    assert (d["slots"]["district"], d["slots"]["town"]) == ("Gampaha", "Negombo")
    d = chat.say("ne ne, Galle")
    assert d["slots"]["district"] == "Galle" and "town" not in d["slots"]


def test_dont_know_is_not_asked_again(client, real_mode, intent_schema):
    chat = Chat(client)
    real_mode["mage ID eka nathi una"] = ("nic_replace_lost", 0.9)
    real_mode["i dont know"] = ("out_of_scope", 0.7)
    chat.say("mage ID eka nathi una")
    assert chat.reply == ASK["district"]["en"]
    d = chat.say("i dont know")
    assert d["slots"]["district"] == "unknown"
    assert d["missing_slots"] == ["urgency"]
    assert d["reply"] == ASK["urgency"]["en"]
    assert d["intent"]["entities"]["district"] is None          # "unknown" is not sent as a district


def test_i_dont_know_does_not_fill_applicant_self(client, real_mode):
    chat = Chat(client)
    real_mode["passport ekak ganna one"] = ("passport_new", 0.8)
    real_mode["i dont know"] = ("passport_new", 0.5)
    chat.say("passport ekak ganna one")                         # asks who it is for
    assert chat.reply == ASK["applicant_for"]["en"]
    assert chat.say("i dont know")["slots"]["applicant_for"] == "unknown"


def test_greeting(client, real_mode):
    real_mode["hi"] = ("passport_new", 0.9)                     # never used: greetings skip the model
    d = Chat(client).say("hi")
    assert d["reply"] == REPLIES["greeting"]["en"]
    assert (d["active_intent"], d["route"], d["intent_source"]) == (None, "none", "greeting")
    assert d["intent"]["intent"] == "unknown"


def test_greeting_mid_conversation_keeps_the_request(client, real_mode):
    chat = Chat(client)
    real_mode["mage ID eka nathi una"] = ("nic_replace_lost", 0.9)
    chat.say("mage ID eka nathi una")
    d = chat.say("hello")
    assert d["active_intent"] == "nic_replace_lost"
    assert d["reply"] == f'{REPLIES["greeting_again"]["en"]} {ASK["district"]["en"]}'
    assert d["intent"]["entities"]["service_id"] == "svc:nic"


def test_warmup_loads_the_engine(real_mode):
    assert pipeline._engine is None
    pipeline.warmup()
    assert pipeline._engine is not None
    assert len(pipeline._store) == 0                            # the throwaway turn is not a session


def test_warmup_without_models_does_not_crash(monkeypatch, tmp_path):
    monkeypatch.setenv("STUB_MODE", "false")
    monkeypatch.setenv("C1_MODEL_DIR", str(tmp_path / "missing"))
    monkeypatch.setattr(pipeline, "_engine", None)
    pipeline.warmup()
    assert pipeline._engine is None
