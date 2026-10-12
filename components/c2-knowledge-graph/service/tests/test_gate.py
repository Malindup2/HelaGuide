"""The free check before the model."""

from app.core.extraction.gate import MIN_CHARS, should_extract

MENU = "\n".join(f"* [Item {i}](https://x.gov.lk/p?id={i})" for i in range(40))


def test_a_language_picker_homepage_is_skipped():
    page = "![](https://x.gov.lk/logo.png)\n## Welcome\n* [English](https://x.gov.lk/en)\n* [Sinhala](https://x.gov.lk/si)\n"
    v = should_extract(page)
    assert not v.send and "almost no readable text" in v.reason


def test_a_long_page_with_no_fact_wording_is_skipped():
    page = MENU + "\n" + "The department was founded long ago and is proud of its heritage. " * 20
    v = should_extract(page)
    assert not v.send and "no fee, document or prerequisite" in v.reason and v.signals == "---"


def test_a_page_with_a_fee_is_sent():
    page = MENU + "\nFee for a new card. " + ("Applicants apply at the office in person. " * 12) + "Rs. 1,000.00\n"
    v = should_extract(page)
    assert v.send and "F" in v.signals


def test_a_short_page_with_a_real_signal_is_kept():
    page = ("Documents required: Birth certificate with a photocopy. The application must be "
            "obtained from the Grama Niladhari prior to applying, and handed over in person at "
            "the divisional office during working hours on weekdays only. ") * 2
    assert MIN_CHARS < len(page) < 1_500
    v = should_extract(page)
    assert v.send and "D" in v.signals


def test_menu_words_alone_never_make_a_page_worth_sending():
    page = ("* [Yellow fever vaccination certificate](https://x.gov.lk/p?id=22)\n"
            "* [Visa Fees](https://x.gov.lk/p?id=45)\n") * 30 + "About our history and mission.\n" * 30
    assert not should_extract(page).send
