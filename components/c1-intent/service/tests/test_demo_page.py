"""The C1-only demo page at /demo."""


def test_demo_page_is_served(client):
    r = client.get("/demo")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "/v1/intent/details" in r.text


def test_demo_page_is_not_in_openapi(client):
    assert "/demo" not in client.get("/openapi.json").json()["paths"]
