"""Scenario tests for stage 1: noise stripping, fingerprints, classification."""

import re

import pytest

from app.core.acquisition.fingerprint import (
    ChangeKind,
    classify,
    collapse_repeats,
    fingerprint,
    normalise_text,
    structure_signature,
)


def page(fee="LKR. 10,000.00", docs=("Birth certificate", "National Identity Card"),
         updated="01 September 2026", visitors="84,412", template="a"):
    """A small passport-service page. `template` b rebuilds the markup."""
    items = "".join(f"<li>{d}</li>" for d in docs)
    if template == "a":
        return (
            "<html><body><h1>Ordinary passport</h1>"
            f"<p>Fee for the normal service: {fee}</p>"
            f"<ul>{items}</ul>"
            f"<p>Last updated: {updated}</p><p>Visitors: {visitors}</p>"
            "</body></html>"
        )
    return (
        "<html><body><div><section><h2>Ordinary passport</h2>"
        f"<table><tr><td>Fee for the normal service: {fee}</td></tr></table>"
        f"<ol>{items}</ol></section>"
        f"<footer><span>Last updated: {updated}</span><span>Visitors: {visitors}</span></footer>"
        "</div></body></html>"
    )


def text_of(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def fp(html: str):
    return fingerprint(text_of(html), html)


# ------------------------------------------------------------------ noise stripping
@pytest.mark.parametrize(
    "noisy",
    [
        "Fee LKR 10,000 Last updated: 01 September 2026",
        "Fee LKR 10,000 Last modified 2026-09-01",
        "Fee LKR 10,000 Visitors: 84,412",
        "Fee LKR 10,000 Page views 1203",
        "Fee LKR 10,000 Copyright © 2026",
        "Fee LKR 10,000 sessionid=abc123",
        "Fee LKR 10,000 12 03 2026 14:05:33",
        "Fee LKR 10,000 1234567",  # an unlabelled footer hit counter
    ],
)
def test_noise_is_removed_and_the_fee_survives(noisy):
    assert normalise_text(noisy) == "Fee LKR 10,000"


def test_noise_filter_never_eats_a_fee_after_the_words_last_updated():
    text = "The last updated fee schedule shows LKR 10,000 for normal service"
    assert "LKR 10,000" in normalise_text(text)


@pytest.mark.parametrize(
    "keep",
    [
        "Office hours are 8:30 AM to 4:15 PM",  # a bare clock time is information
        "Pay Rs. 1234567",  # a currency amount is not a counter
        "NIC No: 199012345678",  # a stated identifier is not a counter
        "Call +94112345678",  # a phone number is not a counter
    ],
)
def test_information_is_not_mistaken_for_noise(keep):
    assert normalise_text(keep) == keep


def test_reflow_is_not_a_change():
    assert normalise_text("Fee   LKR\n10,000") == normalise_text("Fee LKR 10,000")


# ---------------------------------------------------------------------- structure
def test_repeated_list_items_collapse():
    one = ["ul", "li", "/li", "/ul"]
    many = ["ul", "li", "/li", "li", "/li", "li", "/li", "/ul"]
    assert collapse_repeats(many) == collapse_repeats(one)


def test_adding_a_list_item_keeps_the_template():
    a = page(docs=("Birth certificate", "National Identity Card"))
    b = page(docs=("Birth certificate", "National Identity Card", "Police report"))
    assert structure_signature(a) == structure_signature(b)


def test_rebuilt_markup_changes_the_template():
    assert structure_signature(page(template="a")) != structure_signature(page(template="b"))


# ----------------------------------------------------------------- classification
def test_first_sight_is_new():
    assert classify(None, fp(page())).kind is ChangeKind.NEW


def test_identical_page_is_unchanged():
    assert classify(fp(page()), fp(page())).kind is ChangeKind.UNCHANGED


def test_date_stamp_and_hit_counter_alone_are_unchanged():
    before = fp(page(updated="01 September 2026", visitors="84,412"))
    after = fp(page(updated="02 September 2026", visitors="84,977"))
    assert classify(before, after).kind is ChangeKind.UNCHANGED


def test_a_corrected_fee_is_content_changed_even_though_length_is_identical():
    result = classify(fp(page(fee="LKR. 10,000.00")), fp(page(fee="LKR. 11,000.00")))
    assert result.kind is ChangeKind.CONTENT_CHANGED
    assert result.detail["char_delta"] == 0  # no structural signal at all
    assert "structure_changed" not in result.detail


def test_an_added_document_with_the_same_template_is_content_changed():
    before = fp(page(docs=("Birth certificate", "National Identity Card")))
    after = fp(page(docs=("Birth certificate", "National Identity Card", "Police report")))
    assert classify(before, after).kind is ChangeKind.CONTENT_CHANGED


def test_a_rebuilt_page_is_structure_changed():
    result = classify(fp(page(template="a")), fp(page(template="b")))
    assert result.kind is ChangeKind.STRUCTURE_CHANGED
    assert result.detail["structure_changed"] is True


def test_a_rebuilt_page_with_identical_wording_is_still_structure_changed():
    a, b = page(template="a"), page(template="b")
    result = classify(fingerprint("same words", a), fingerprint("same words", b))
    assert result.kind is ChangeKind.STRUCTURE_CHANGED
    assert result.detail["content_also_changed"] is False


def test_fingerprint_round_trips_through_a_dict():
    f = fp(page())
    assert type(f).from_dict(f.to_dict()) == f
