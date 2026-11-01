"""context_strategy and context_tokens: only in the C1-only /v1/intent/details response, never in the /v1/intent contract."""
import jsonschema


def _details(client, sid, text, bot=None):
    r = client.post("/v1/intent/details", json={"session_id": sid, "text": text, "bot_text": bot})
    assert r.status_code == 200, r.text
    return r.json()


def test_details_reports_the_context_window_and_its_tokens(client, real_mode):
    real_mode["mata passport ekak ganna one"] = ("passport_new", 0.9)
    first = _details(client, "anon-ctx1", "mata passport ekak ganna one")
    assert first["context_strategy"] == "window_3"
    assert first["context_tokens"] == 5 + 2                       # fake tokenizer: words + <s> </s>
    second = _details(client, "anon-ctx1", "normal", "Normal da urgent da?")
    assert second["context_tokens"] == (5 + 2) + (1 + 2)         # the window now holds both messages
    for text in ("Galle", "next year", "ow"):
        last = _details(client, "anon-ctx1", text)
    assert last["context_tokens"] == (1 + 2) + (2 + 2) + (1 + 2)  # only the last 3 messages: the window stays flat


def test_greeting_does_not_run_the_intent_model(client, real_mode):
    assert _details(client, "anon-ctx2", "hi")["context_tokens"] == 0


def test_contract_response_is_unchanged(client, real_mode, intent_schema):
    real_mode["mata passport ekak ganna one"] = ("passport_new", 0.9)
    r = client.post("/v1/intent", json={"session_id": "anon-ctx3", "text": "mata passport ekak ganna one"})
    assert r.status_code == 200
    body = r.json()
    assert "context_tokens" not in body and "context_strategy" not in body
    jsonschema.validate(body, intent_schema)


def test_stub_details_include_the_fields(client):
    d = _details(client, "anon-ctx4", "mata passport ekak ganna one")
    assert d["context_strategy"] == "window_3" and d["context_tokens"] == 0


def test_demo_page_shows_the_token_count(client):
    page = client.get("/demo").text
    assert "d.context_tokens" in page and "d.context_strategy" in page
