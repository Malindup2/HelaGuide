"""Active-intent locking, per-intent slot state and bot replies (engine.Session), with the fake engine.

Each conversation sends the previous turn's `reply` back as `bot_text`, the way the demo page does.
The fake engine tags every Latin-script word EN, so replies come in English here (Singlish with the real model).
"""
import pytest

from app.core.engine import ASK, REPLIES, reply_language


class Chat:
    def __init__(self, client, session_id="anon-1"):
        self.client, self.session_id, self.reply = client, session_id, None

    def say(self, text, bot_text="previous reply"):
        bot = self.reply if bot_text == "previous reply" else bot_text
        r = self.client.post("/v1/intent/details", json={"session_id": self.session_id, "text": text, "bot_text": bot})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["reply"].strip(), f"empty reply for {text!r}"
        self.reply = d["reply"]
        return d


# the conversation that lost the passport request; the fake model misreads every turn after the first
REGRESSION = [
    ("passport ekak mata ganna puluwnda", ("passport_new", 0.55)),     # first turn: 0.5 is enough to lock
    ("normal", ("nic_replace_lost", 0.9)),                             # answer to "Normal da urgent da?"
    ("next year, mata wayasa 14i", ("nic_new", 0.85)),                 # answer to "Kawadada travel karanne?"
    ("next year", ("passport_renew", 0.8)),                            # confident, but names no service
    ("ganna puluwnda", ("out_of_scope", 0.3)),                         # below min confidence
    ("galle", ("birth_cert_copy", 0.7)),                               # under the switch threshold
]


def test_regression_passport_stays_active(client, real_mode):
    chat = Chat(client)
    for text, prediction in REGRESSION:
        real_mode[text] = prediction
    turns = [chat.say(text) for text, _ in REGRESSION]

    assert [d["active_intent"] for d in turns] == ["passport_new"] * 6
    assert [d["internal_intent"] for d in turns] == ["passport_new"] * 6
    assert all(d["route"] == "orchestration" for d in turns)
    assert [d["slots"].get("service_type") for d in turns] == [None] + ["normal"] * 5
    assert [d["intent_locked"] for d in turns] == [False, True, True, True, True, True]
    assert turns[0]["reply"] == ASK["service_type"]["en"]
    assert turns[1]["reply"] == ASK["travel_date"]["en"]
    assert turns[2]["slots"] == {"applicant_for": "self", "service_type": "normal", "travel_date": "next year"}
    assert [d["ready"] for d in turns] == [False, False, True, True, True, True]
    assert turns[-1]["slots"]["district"] == "Galle"          # "galle" kept as context for the passport request
    assert turns[-1]["reply"] == ("Okay — normal new passport, for you, in Galle, travelling next year. "
                                  "I'll show you the documents you need.")
    # the contract keeps sending the passport request
    assert turns[-1]["intent"]["intent"] == "apply_service"
    assert turns[-1]["intent"]["entities"]["service_id"] == "svc:passport"


def test_real_switch_carries_only_district_and_switch_back_restores(client, real_mode):
    real_mode.update({
        "mata passport ekak ganna one, mama galle inne": ("passport_new", 0.8),
        "normal": ("passport_new", 0.7),
        "next year": ("passport_new", 0.7),
        "NIC ekath aluthen ganna one": ("nic_new", 0.9),
        "passport eka gana aye kiyannako": ("passport_new", 0.9),
    })
    chat = Chat(client)
    chat.say("mata passport ekak ganna one, mama galle inne")
    chat.say("normal")
    assert chat.say("next year")["ready"] is True

    d = chat.say("NIC ekath aluthen ganna one")
    assert (d["active_intent"], d["internal_intent"], d["intent_locked"]) == ("nic_new", "nic_new", False)
    assert d["slots"] == {"district": "Galle"}          # new frame: only district, said under passport
    assert d["assumed_slots"] == ["district"]
    assert d["missing_slots"] == ["applicant_for", "date_of_birth"]
    assert d["intent"]["entities"] == {"service_id": "svc:nic", "district": "Galle"}

    # bot_text=None: the NIC date-of-birth question is pending, and a slot answer never switches
    d = chat.say("passport eka gana aye kiyannako", bot_text=None)
    assert d["active_intent"] == "passport_new"
    assert d["slots"] == {"applicant_for": "self", "service_type": "normal", "travel_date": "next year",
                          "district": "Galle"}
    assert d["ready"] is True


def test_windowed_prediction_does_not_switch_on_a_slot_answer(client, real_mode):
    real_mode["passport ekak ganna one"] = ("passport_new", 0.8)
    real_mode["NIC eke tiyena widihata"] = ("nic_new", 0.95)
    real_mode[("current", "NIC eke tiyena widihata")] = ("passport_new", 0.6)     # alone it is not an NIC request
    chat = Chat(client)
    chat.say("passport ekak ganna one")                     # asks "Normal da urgent da?"
    d = chat.say("NIC eke tiyena widihata")
    assert (d["active_intent"], d["internal_intent"], d["intent_source"]) == ("passport_new", "passport_new", "active_intent")


def test_complaint_mid_conversation_keeps_active_intent(client, real_mode):
    complaint = "oya kiwwa office eka saturday open kiyala, mama giyama wahala thibbe"
    real_mode.update({
        "mata passport ekak ganna one": ("passport_new", 0.8),
        "normal": ("passport_new", 0.7),
        complaint: ("feedback_complaint", 0.9),
        "next year": ("passport_new", 0.7),
    })
    chat = Chat(client)
    chat.say("mata passport ekak ganna one")
    chat.say("normal")
    d = chat.say(complaint)
    assert (d["internal_intent"], d["route"]) == ("feedback_complaint", "trust_verification")
    assert d["active_intent"] == "passport_new"
    assert d["ready"] is False
    assert d["slots"]["service_mentioned"] == "passport"
    assert d["reply"] == f'{REPLIES["complaint"]["en"]} {ASK["travel_date"]["en"]}'   # resumes with the pending question
    assert d["intent"]["entities"]["service_id"] == "svc:passport"     # the contract still projects the passport

    d = chat.say("next year")
    assert (d["internal_intent"], d["active_intent"], d["ready"]) == ("passport_new", "passport_new", True)
    assert d["slots"]["service_type"] == "normal"


def test_low_confidence_turn_fills_the_active_intent(client, real_mode):
    real_mode["passport ekak ganna one"] = ("passport_new", 0.8)
    real_mode["ikmanata"] = ("nic_replace_lost", 0.2)
    chat = Chat(client)
    chat.say("passport ekak ganna one")
    d = chat.say("ikmanata")
    assert (d["internal_intent"], d["intent_source"], d["intent_locked"]) == ("passport_new", "previous_topic", True)
    assert d["slots"]["service_type"] == "urgent"


def test_unsure_first_turn_asks_which_service(client, real_mode):
    real_mode["mata udaw ekak one"] = ("passport_new", 0.4)
    d = Chat(client).say("mata udaw ekak one")
    assert d["active_intent"] is None
    assert d["reply"] == REPLIES["clarify"]["en"]


def test_lock_needs_point_six_after_the_first_turn(client, real_mode):
    real_mode["mokakda me"] = ("out_of_scope", 0.9)
    real_mode["passport ekak"] = ("passport_new", 0.55)
    chat = Chat(client)
    chat.say("mokakda me")
    assert chat.say("passport ekak")["active_intent"] is None


@pytest.mark.parametrize("intent, confidence", [
    ("unsupported_service", 0.9), ("out_of_scope", 0.9), ("general_question", 0.9),
    ("feedback_complaint", 0.9), ("unknown", 0.9), ("nic_new", 0.1),
])
def test_every_first_turn_gets_a_reply(client, real_mode, intent, confidence):
    real_mode["some text"] = (intent, confidence)
    assert Chat(client).say("some text")["reply"].strip()


@pytest.mark.parametrize("tags, language, expected", [
    ([("ne", "SI"), ("ne", "SI"), ("Galle", "NE")], "si", "mixed"),    # romanized Sinhala is tagged SI
    ([("ගාල්ලේ", "SI")], "si", "si"),
    ([("I", "EN"), ("want", "EN"), ("a", "EN"), ("passport", "EN")], "en", "en"),
    ([("mata", "SI"), ("ID", "EN"), ("එක", "SI")], "mixed", "mixed"),
])
def test_reply_language_follows_the_script(tags, language, expected):
    assert reply_language(tags, language) == expected
