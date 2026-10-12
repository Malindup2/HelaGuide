from app.core.knowledge.chunks import _or_query, _terms, chunk_page, find_contacts

MD = """# Contact Details
##### Call centre
You can phone between 8.30 a.m. and 4.15 p.m. on weekdays about your identity card.

##### Head Office
| 1 | Deputy Commissioner Oneday service branch | 0115226113 | ac_ods@drp.lk |
"""


def test_a_chunk_keeps_its_heading_and_never_crosses_one():
    title, chunks = chunk_page(MD)
    assert title == "Contact Details"
    assert [c.heading for c in chunks] == ["Call centre", "Head Office"]
    assert "0115226113" in chunks[1].text


def test_link_urls_are_dropped_but_link_text_stays():
    _, chunks = chunk_page("## Offices\nSee [the Galle office](https://x.lk/galle.php) for help with your card here.")
    assert "the Galle office" in chunks[0].text and "https://" not in chunks[0].text


def test_a_page_marker_from_a_pdf_is_not_taken_as_the_title():
    title, chunks = chunk_page("## Page 1\nSome real policy text that is long enough to keep around.\n## Page 2\nMore text that is also long enough to be kept as a chunk.")
    assert title == ""
    assert [c.heading for c in chunks] == ["page 1", "page 2"]


def test_search_words_widen_with_synonyms_but_drop_filler():
    assert _terms("What is the phone number of the Kurunegala office") == \
        ["phone", "number", "kurunegala", "office"]
    q = _or_query(_terms("phone"))
    assert "telephone" in q and "|" in q


CONTACTS = [
    {"kind": "phone", "label": "Provincial office - North West", "value": "037 222 4337",
     "page_url": "https://x.lk/en/kurunegala.php", "source_url": "https://x.lk/en/contact.php"},
    {"kind": "phone", "label": "Provincial Office - East", "value": "0652229449",
     "page_url": "https://x.lk/en/baticoloa.php", "source_url": "https://x.lk/en/contact.php"},
    {"kind": "email", "label": "Provincial Office - East", "value": "info.bat@x.lk",
     "page_url": "https://x.lk/en/baticoloa.php", "source_url": "https://x.lk/en/contact.php"},
    {"kind": "hours", "label": "Call centre hours", "value": "8.30 a.m. to 4.15 p.m., weekdays",
     "page_url": None, "source_url": "https://x.lk/en/contact.php"},
]


def test_a_place_name_that_only_appears_in_the_page_link_still_finds_the_office():
    got = find_contacts(CONTACTS, "phone number of the Kurunegala office")
    assert [c["value"] for c in got] == ["037 222 4337"]


def test_the_kind_asked_for_filters_the_answer():
    got = find_contacts(CONTACTS, "email of the east office")
    assert [c["value"] for c in got] == ["info.bat@x.lk"]


def test_american_spelling_finds_the_british_label():
    assert find_contacts(CONTACTS, "call center hours")[0]["kind"] == "hours"
