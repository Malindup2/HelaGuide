"""The rules that decide which waiting facts need no person."""

from app.core.graph.autoreview import AUTO, Row, classify


def row(**kw):
    base = dict(staged_id=1, fact_id="svc:nic:fee:standard", service_id="svc:nic", predicate="fee",
                value_text="Rs. 500.00", value_num=500.0, unit="LKR",
                evidence="A fee of Rs. 500.00 has to be paid.", detail={}, service_known=True,
                approved_value=None, rivals=0)
    base.update(kw)
    return Row(**base)


def ok(**kw):
    return classify(row(**kw))[0]


def why(**kw):
    return classify(row(**kw))[1]


def test_a_clean_fee_for_a_known_service_is_approved():
    assert ok()


def test_the_same_value_already_in_the_graph_is_still_clean():
    assert ok(approved_value="Rs. 500.00")


def test_a_changed_value_always_waits_for_a_person():
    assert not ok(approved_value="Rs. 300.00")
    assert "changed" in why(approved_value="Rs. 300.00")


def test_a_new_service_is_approved_automatically_unless_the_setting_is_turned_off(monkeypatch):
    import app.core.graph.autoreview as ar

    assert ok(service_known=False)
    monkeypatch.setattr(ar, "AUTO_NEW_SERVICES", False)
    assert not ok(service_known=False)


def test_a_link_from_a_service_about_the_item_to_the_item_waits():
    assert not ok(predicate="prerequisite", fact_id="svc:passport_alteration:prerequisite:passport",
                  service_id="svc:passport_alteration", value_text="svc:passport", value_num=None,
                  unit=None, detail={"requires_service": "svc:passport"},
                  evidence="Current passport with a photocopy of the Bio data page")
    assert ok(predicate="prerequisite", fact_id="svc:marriage_registration:prerequisite:birth_certificate",
              service_id="svc:marriage_registration", value_text="svc:birth_certificate", value_num=None,
              unit=None, detail={"requires_service": "svc:birth_certificate"},
              evidence="Birth certificate of the bride")


def test_two_different_waiting_values_for_one_position_wait():
    assert not ok(rivals=1)


def test_free_text_is_never_automatic():
    assert not ok(predicate="eligibility", value_text="Only the mother may collect")


def test_blanks_and_labels_are_not_facts():
    assert not ok(value_text="RS…………..", value_num=None, unit=None)
    assert not ok(predicate="fee", value_text="one-day service fee", value_num=None, unit=None)
    assert not ok(predicate="processing_time", value_text="Standard service")
    assert not ok(predicate="document", value_text="2.")


def test_a_fact_that_holds_only_in_some_cases_waits():
    assert not ok(predicate="document", fact_id="svc:nic:document:x", value_text="Police report",
                  evidence="if the card was lost, a police report is required", value_num=None, unit=None)


def test_a_derived_link_for_a_card_already_held_waits():
    assert not ok(predicate="prerequisite", fact_id="svc:s:prerequisite:nic", value_text="svc:nic",
                  value_num=None, unit=None, detail={"requires_service": "svc:nic"},
                  evidence="The National Identity card of the deceased person", service_id="svc:surrender_nic_deceased")


def test_a_plain_derived_link_is_clean():
    assert ok(predicate="prerequisite", fact_id="svc:passport:prerequisite:nic", value_text="svc:nic",
              value_num=None, unit=None, detail={"requires_service": "svc:nic"},
              evidence="A copy of the National Identity Card", service_id="svc:passport")


def test_auto_decisions_carry_a_name_that_cannot_be_mistaken_for_a_person():
    assert AUTO == "auto-rules"


def test_the_graph_writer_and_the_rules_agree_on_the_automatic_reviewer_name():
    from app.core.graph.writer import AUTO_REVIEWER

    assert AUTO_REVIEWER == AUTO


def test_a_fee_in_a_table_with_no_currency_in_the_cell_is_still_an_amount():
    assert ok(value_text="1000.00", value_num=1000.0, unit=None)
    assert ok(value_text="US$ 20", value_num=20.0, unit=None)


def test_free_of_charge_is_a_valid_fee_but_a_row_of_dots_is_not():
    assert ok(value_text="FOC", value_num=None, unit=None)
    assert not ok(value_text="RS.......", value_num=None, unit=None)


def test_in_duplicate_meaning_two_copies_is_not_a_surrender_or_loss_signal():
    assert ok(predicate="prerequisite", fact_id="svc:marriage:prerequisite:nic",
              service_id="svc:registration_of_marriages_general", value_text="svc:nic",
              value_num=None, unit=None, detail={"requires_service": "svc:nic"},
              evidence="The Notice of Marriage must be written in duplicate, certified, and handed over")


def test_a_genuine_duplicate_certificate_still_holds():
    assert not ok(predicate="prerequisite", fact_id="svc:nic:prerequisite:nic",
                  service_id="svc:nic_duplicate", value_text="svc:nic", value_num=None, unit=None,
                  detail={"requires_service": "svc:nic"},
                  evidence="Apply for a duplicate certificate if the original is lost")
