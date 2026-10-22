import pytest

from app.core.validator import (INTENTS, OTHER, Rejected, canonical_value, check_turn, confirm_ready, merge_slots)

BIRTH = "birth_cert_copy"


def llm(**kw):
    out = {"reply": "Hari!", "dialogue_act": "slot_answer", "active_intent": BIRTH, "tasks": [BIRTH],
           "slot_updates": {}, "ready_to_confirm": False}
    out.update(kw)
    return out


def reasons(result):
    return {(r.field, r.reason) for r in result.rejections}


# ---------------------------------------------------------------- check_turn
def test_twelve_internal_intents():
    assert len(INTENTS) == 12 and "unsupported_service" in INTENTS and "unknown" not in INTENTS


def test_valid_turn_passes():
    t = check_turn(llm(reply="  Kurunegala neda?  "), "nic_new")
    assert (t.dialogue_act, t.intent, t.intent_source, t.tasks, t.reply) == \
        ("slot_answer", BIRTH, "llm", [BIRTH], "Kurunegala neda?")
    assert t.rejections == []


@pytest.mark.parametrize("bad", ["driving_licence", "Birth_Cert_Copy", 3])
def test_invalid_intent_falls_back_to_xlmr(bad):
    t = check_turn(llm(active_intent=bad), "passport_new")
    assert (t.intent, t.intent_source) == ("passport_new", "nlu_fallback")
    assert ("active_intent", "unknown_intent") in reasons(t)


def test_null_intent_means_no_request_and_is_not_a_rejection():
    t = check_turn(llm(active_intent=None, dialogue_act="greet"), "unknown")
    assert (t.intent, t.intent_source, t.rejections) == ("unknown", "nlu_fallback", [])


def test_invalid_intent_and_unknown_xlmr_gives_unknown():
    assert check_turn(llm(active_intent="nope"), "unknown").intent == "unknown"


def test_bad_act_tasks_reply_and_ready_are_rejected():
    t = check_turn(llm(dialogue_act="dance", tasks=[BIRTH, "nope", BIRTH, "unsupported_service"], reply="",
                       ready_to_confirm="yes"), BIRTH)
    assert t.dialogue_act is None
    assert t.tasks == [BIRTH, "unsupported_service"]
    assert t.reply is None
    assert t.ready_claim is False
    assert reasons(t) == {("dialogue_act", "unknown_act"), ("tasks", "unknown_intent"), ("reply", "empty_reply"),
                          ("ready_to_confirm", "not_a_bool")}


# ---------------------------------------------------------------- canonical values
@pytest.mark.parametrize("slot, value, expected", [
    ("district", "kurunagala district", ("Kurunegala", None)),
    ("district", "කුරුණෑගල", ("Kurunegala", None)),
    ("district", "Moratuwa", ("Colombo", None)),            # a town -> its district
    ("travel_date", "mid December", ("mid December", None)),
    ("date_of_birth", "2001-04-12", ("2001-04-12", None)),      # ISO first
    ("travel_date", "2026-12-15", ("2026-12-15", None)),
    ("date", "15/12/2026", ("15/12/2026", None)),                # date matcher as fallback
    ("applicant_for", "parent", ("parent", None)),
    ("applicant_for", "my mother", ("parent", None)),
    ("change_field", "Address", ("address", None)),
    ("service_type", "one_day", ("urgent", None)),
    ("urgency", "normal", ("normal", None)),
    ("purpose", "for school admission", ("school admission", None)),
    ("purpose", "business registration", (OTHER, "business registration")),
    ("issue", "the fees were higher", ("fee different", None)),
    ("service_mentioned", "driving licence", ("driving license", None)),
    ("service_mentioned", "pension office", ("pension office", None)),
    ("new_value", " 12 Lake Road, Sample Town ", ("12 Lake Road, Sample Town", None)),
    ("district", "unknown", ("unknown", None)),
])
def test_canonical_values(slot, value, expected):
    assert canonical_value(slot, value) == expected


@pytest.mark.parametrize("slot, value, reason", [
    ("district", "Narnia", "not_a_district"),
    ("travel_date", "soon-ish", "not_a_date"),
    ("travel_date", "2026-02-30", "not_a_date"),                 # ISO shape, not a real day
    ("travel_date", "next friday", "not_a_date"),                # the prompt asks the LLM to resolve these
    ("applicant_for", "the neighbour's cat", "not_an_enum_value"),
    ("purpose", ["school"], "not_a_string"),
    ("purpose", True, "not_a_string"),
    ("new_value", "x" * 500, "too_long"),
])
def test_bad_values_are_rejected(slot, value, reason):
    with pytest.raises(Rejected, match=reason):
        canonical_value(slot, value)


# ---------------------------------------------------------------- merge_slots
def test_several_slots_from_one_message():
    m = merge_slots(BIRTH, {"applicant_for": "parent", "district": "Kurunegala", "purpose": "business registration"},
                    "slot_answer", prev={})
    assert m.slots == {"applicant_for": "parent", "district": "Kurunegala", "purpose": OTHER}
    assert m.raw == {"purpose": "business registration"}
    assert (m.missing_slots, m.ready, m.proposed, m.rejections) == ([], True, 3, [])


def test_greeting_with_no_updates_changes_nothing():
    prev = {"applicant_for": "parent"}
    m = merge_slots(BIRTH, {}, "greet", prev)
    assert m.slots == prev and m.accepted == {} and m.proposed == 0
    assert m.missing_slots == ["district", "purpose"] and not m.ready


def test_nulls_are_not_mentions():
    m = merge_slots(BIRTH, {"district": None, "purpose": ""}, "slot_answer", {})
    assert m.slots == {} and m.proposed == 0 and m.rejections == []


def test_slot_of_another_intent_is_rejected():
    m = merge_slots(BIRTH, {"travel_date": "next month", "district": "Galle"}, "slot_answer", {})
    assert m.slots == {"district": "Galle"}
    assert reasons(m) == {("travel_date", "slot_not_in_intent")}
    assert m.proposed == 2


def test_invalid_district_is_rejected_and_old_value_kept():
    m = merge_slots(BIRTH, {"district": "Narnia"}, "correction", {"district": "Galle"})
    assert m.slots == {"district": "Galle"}
    assert reasons(m) == {("district", "not_a_district")}


def test_slot_updates_not_a_dict():
    m = merge_slots(BIRTH, ["district", "Galle"], "slot_answer", {})
    assert m.slots == {} and reasons(m) == {("slot_updates", "not_an_object")}


def test_conflict_extractive_rules_value_wins():
    m = merge_slots(BIRTH, {"district": "Kandy"}, "slot_answer", prev={}, rules_changes={"district": "Matale"})
    assert m.slots["district"] == "Matale"
    [c] = m.conflicts
    assert (c.slot, c.rules, c.llm, c.kept, c.reason) == ("district", "Matale", "Kandy", "rules", "extractive_match")


def test_conflict_non_extractive_llm_value_wins():
    m = merge_slots(BIRTH, {"purpose": "bank"}, "correction", prev={}, rules_changes={"purpose": "school admission"})
    assert m.slots["purpose"] == "bank"
    assert [(c.slot, c.kept) for c in m.conflicts] == [("purpose", "llm")]


def test_agreeing_values_are_no_conflict():
    m = merge_slots(BIRTH, {"district": "kurunagala"}, "slot_answer", {}, rules_changes={"district": "Kurunegala"})
    assert m.conflicts == [] and m.slots["district"] == "Kurunegala"


def test_rules_changes_alone_are_applied():
    m = merge_slots(BIRTH, {}, "slot_answer", {"applicant_for": "child"}, rules_changes={"district": "Galle"})
    assert m.slots == {"applicant_for": "child", "district": "Galle"}


def test_purpose_correction_replaces_other_and_drops_raw():
    m = merge_slots(BIRTH, {"purpose": "school"}, "correction", {"purpose": OTHER})
    assert m.slots["purpose"] == "school admission" and m.raw == {}


def test_applicant_for_protected_from_llm_overwrite():
    m = merge_slots(BIRTH, {"applicant_for": "child"}, "slot_answer", {"applicant_for": "parent"})
    assert m.slots["applicant_for"] == "parent"
    assert "applicant_for" not in m.accepted
    assert [(r.field, r.reason, r.source) for r in m.rejections] == \
        [("applicant_for", "protected_without_correction", "llm")]


def test_applicant_for_protected_from_rules_overwrite():
    m = merge_slots(BIRTH, {}, "new_request", {"applicant_for": "parent"}, rules_changes={"applicant_for": "self"})
    assert m.slots["applicant_for"] == "parent"
    assert [(r.reason, r.source) for r in m.rejections] == [("protected_without_correction", "rules")]


def test_rules_protection_can_be_turned_off_but_llm_stays_protected():
    m = merge_slots(BIRTH, {}, "new_request", {"applicant_for": "parent"}, rules_changes={"applicant_for": "self"},
                    protect_rules=False)
    assert m.slots["applicant_for"] == "self" and m.rejections == []
    m = merge_slots(BIRTH, {"applicant_for": "child"}, "slot_answer", {"applicant_for": "parent"},
                    protect_rules=False)
    assert m.slots["applicant_for"] == "parent"
    assert [(r.reason, r.source) for r in m.rejections] == [("protected_without_correction", "llm")]


def test_applicant_for_changes_on_correction():
    m = merge_slots(BIRTH, {"applicant_for": "child"}, "correction", {"applicant_for": "parent"})
    assert m.slots["applicant_for"] == "child" and m.rejections == []


def test_applicant_for_unknown_can_be_filled():
    m = merge_slots(BIRTH, {"applicant_for": "spouse"}, "slot_answer", {"applicant_for": "unknown"})
    assert m.slots["applicant_for"] == "spouse"


def test_conflict_log_has_no_values(caplog):
    caplog.set_level("INFO", logger="c1-intent")
    merge_slots("nic_update", {"new_value": "12 Lake Road"}, "correction", {},
                rules_changes={"new_value": "14 Hill Street"})
    assert "validator conflict" in caplog.text
    assert "Lake" not in caplog.text and "Hill" not in caplog.text


def test_intent_without_slots_is_never_ready():
    m = merge_slots("out_of_scope", {"district": "Galle"}, "out_of_scope", {})
    assert m.slots == {} and not m.ready


@pytest.mark.parametrize("claim, ready, expected, rejected", [
    (True, True, True, False), (False, True, False, False), (True, False, False, True), (False, False, False, False)])
def test_ready_to_confirm_only_when_nothing_is_missing(claim, ready, expected, rejected):
    value, rejection = confirm_ready(claim, ready)
    assert value is expected
    assert (rejection is not None) is rejected
    if rejection:
        assert (rejection.field, rejection.reason) == ("ready_to_confirm", "slots_missing")


def test_ready_comes_from_missing_slots():
    m = merge_slots(BIRTH, {"district": "Galle"}, "slot_answer", {"applicant_for": "child"})
    assert m.missing_slots == ["purpose"] and m.ready is False
    m = merge_slots(BIRTH, {"purpose": "visa"}, "slot_answer", m.slots)
    assert m.missing_slots == [] and m.ready is True


# ---------------------------------------------------------------- raw text for a bare "other"
def test_bare_other_takes_the_llms_slot_raw():
    m = merge_slots(BIRTH, {"purpose": "other"}, "slot_answer", {}, raw_values={"purpose": " business reg "},
                    message="business reg purpose")
    assert (m.slots["purpose"], m.raw) == (OTHER, {"purpose": "business reg"})


@pytest.mark.parametrize("raw_values", [None, {}, {"purpose": ""}, {"purpose": "other"}, {"purpose": 5}])
def test_bare_other_without_usable_slot_raw_takes_the_message(raw_values):
    m = merge_slots(BIRTH, {"purpose": "Other"}, "slot_answer", {}, raw_values=raw_values,
                    message="  business   reg purpose ")
    assert (m.slots["purpose"], m.raw) == (OTHER, {"purpose": "business reg purpose"})


def test_other_with_words_keeps_its_own_words_and_slot_raw_only_matters_for_other():
    m = merge_slots(BIRTH, {"purpose": "business registration", "district": "Galle"}, "slot_answer", {},
                    raw_values={"purpose": "ignored", "district": "ignored"}, message="x")
    assert m.raw == {"purpose": "business registration"} and m.slots["district"] == "Galle"


def test_issue_other_too_but_not_free_text_slots():
    m = merge_slots("feedback_complaint", {"issue": "other", "service_mentioned": "other"}, "slot_answer", {},
                    message="they were rude")
    assert m.raw == {"issue": "they were rude"} and m.slots["service_mentioned"] == "other"


def test_slot_raw_not_an_object_is_rejected():
    m = merge_slots(BIRTH, {"purpose": "other"}, "slot_answer", {}, raw_values=["business"], message="biz")
    assert m.raw == {"purpose": "biz"}
    assert ("slot_raw", "not_an_object") in reasons(m)
