"""The hand-written word lists: language, kind of fact, claimed value, support or dispute."""
from app.core.lexicon import (detect_language, detect_predicate, extract_claimed, infer_kind,
                              qualifier_hits, specificity_features)


def test_language_detection():
    assert detect_language("The fee was 12,000") == "en"
    assert detect_language("passport eke fee eka 12000 kiwwa") == "mixed"
    assert detect_language("ගමන් බලපත්‍රය ලබාගන්න දින 30ක් ගියා.") == "si"


def test_predicate_detection():
    assert detect_predicate(["They charged me Rs. 1,500 for it"])[0] == "fee"
    assert detect_predicate(["They also asked for a medical certificate"])[0] == "document"
    assert detect_predicate(["It took 30 days to get it"])[0] == "processing_time"
    assert detect_predicate(["hello"])[0] is None


def test_the_word_report_alone_is_not_a_document_hint():
    # "I need to report a problem about the fee" must read as a fee message
    assert detect_predicate(["I need to report a problem about the fee."])[0] == "fee"
    assert detect_predicate(["They asked for a police report."])[0] == "document"


def test_claimed_value_is_the_number_that_is_not_the_stored_one():
    assert extract_claimed("it was 12,000, not 11,000 as you said", "", 11000.0, None)[0] == 12000.0
    assert extract_claimed("they charged 500", "", 0.0, None)[0] == 500.0
    assert extract_claimed("fee was different", "", 11000.0, None)[0] is None
    assert extract_claimed("whatever", "", 11000.0, "12,000")[0] == 12000.0      # a hint wins


def test_support_versus_dispute():
    assert infer_kind("charged 11,000 as listed, that was correct", 11000.0, 11000.0) == "support"
    assert infer_kind("it was 12,000 not 11,000 as you said", 12000.0, 11000.0) == "dispute"
    assert infer_kind("fee was different", None, 11000.0) == "dispute"


def test_qualifiers_and_specificity():
    assert qualifier_hits("the one day service", ["normal", "one_day"]) == {"one_day"}
    assert qualifier_hits("my child's passport", ["normal", "minor_normal"]) == {"minor_normal"}
    f = specificity_features("I went to the Colombo office yesterday and was charged 4000 for it.", "", 4000.0, False)
    assert f == {"value": True, "when": True, "where": True, "detail": True}
    assert not any(specificity_features("fee different", "", None, False).values())
