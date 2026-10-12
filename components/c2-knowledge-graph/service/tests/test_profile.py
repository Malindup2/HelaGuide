from app.core.graph.profile import parse_contacts, parse_forms, _phones

PAGE = "https://x.gov.lk/en/contact.php"
MD = """
you can phone the numbers indicated below between 8.30 a.m. and 4.15 p.m. on weekdays.
Telephone :
  * for inquiries regarding card details : (011)5226126
  * for other details : (011)5226100

Fax : (011) 2862290
email : info@x.lk
Department for Registration of Persons,
Suhurupaya,
Subuthipura rd,
Battaramulla.
#### Useful Links
"""
HTML = """<table><tr><th>No</th><th>Name</th><th>Telephone</th><th>Fax</th><th>email</th></tr>
<tr><td>1</td><td>Mr. Some Person<br>Deputy Commissioner<br><a href="/en/ods.php">Oneday service branch</a></td>
<td>0115226113<br>0115226108</td><td></td><td>ac_ods@x.lk</td></tr></table>"""


def by(items, kind):
    return [i for i in items if i["kind"] == kind]


def test_department_contacts_hours_and_address_are_read_with_their_line():
    items = parse_contacts("", MD, PAGE)
    assert by(items, "hours")[0]["value"] == "8.30 a.m. to 4.15 p.m., weekdays"
    assert {i["value"] for i in by(items, "phone")} == {"(011)5226126", "(011)5226100"}
    assert by(items, "fax")[0]["value"] == "(011) 2862290"
    assert by(items, "email")[0]["value"] == "info@x.lk"
    assert "Subuthipura rd" in by(items, "address")[0]["value"]
    assert all(i["evidence"] and i["source_url"] == PAGE for i in items)


def test_a_branch_row_keeps_the_role_and_both_numbers_but_not_the_person():
    items = parse_contacts(HTML, "", PAGE)
    phones = by(items, "phone")
    assert [p["value"] for p in phones] == ["0115226113", "0115226108"]
    assert "Deputy Commissioner" in phones[0]["label"] and "Oneday" in phones[0]["label"]
    assert not any("Some Person" in str(i) for i in items)
    assert by(items, "email")[0]["value"] == "ac_ods@x.lk"


def test_two_numbers_on_separate_lines_stay_two_numbers():
    assert _phones(["0112862259", "0115226107"]) == ["0112862259", "0115226107"]


def test_form_links_come_from_the_table_and_a_link_back_to_the_page_is_skipped():
    md = """##### **Forms and Guidelines**
|  &nbsp Application for a card   |  [](https://x.gov.lk/en/assets/application.pdf)  |
|  &nbsp A form with no file   |  [](https://x.gov.lk/en/downloads.php)  |
##### **Acts and regulations**
|  &nbsp The Act   |  [](https://x.gov.lk/en/assets/act.pdf)  |
"""
    forms = parse_forms(md, "https://x.gov.lk/en/downloads.php")
    assert [(f["label"], f["section"]) for f in forms] == [("Application for a card", "forms"),
                                                           ("The Act", "acts")]
