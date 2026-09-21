def test_intent_stub(client):
    r = client.post("/v1/intent", json={"session_id": "anon-test", "text": "mata passport ekak ganna one"})
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "anon-test"
    assert body["entities"]["service_id"] == "svc:passport"
