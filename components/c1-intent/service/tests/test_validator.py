import pytest

from app.core.validator import (INTENTS, OTHER, Rejected, canonical_value, check_turn, merge_slots)

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


@pytest.mark.parametrize("bad", ["driving_licence", None, "Birth_Cert_Copy", 3])
def test_invalid_intent_falls_back_to_xlmr(bad):
    t = check_turn(llm(active_intent=bad), "passport_new")
    assert (t.intent, t.intent_source) == ("passport_new", "nlu_fallback")
    assert ("active_intent", "unknown_intent") in reasons(t)


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
    ("date_of_birth", "2001-04-12", ("2001-04-12", None)),
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
