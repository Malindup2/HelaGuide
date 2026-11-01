"""The C1-only demo page at /demo."""


def test_demo_page_is_served(client):
    r = client.get("/demo")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "/v1/intent/details" in r.text


def test_demo_page_can_switch_to_chat_and_details_stays_the_default(client):
    page = client.get("/demo").text
    assert '<select id="endpoint">' in page and '"/v1/chat"' in page
    details_opt = page.index('<option value="details">')
    assert details_opt < page.index('<option value="chat">')     # first option = the default
    assert "selected" not in page[details_opt:page.index("</select>")]
    assert "d.dialogue_source" in page and "tt.res.dialogue_source" in page


def test_demo_page_is_not_in_openapi(client):
    assert "/demo" not in client.get("/openapi.json").json()["paths"]
