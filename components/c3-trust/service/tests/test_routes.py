def test_feedback_accepted(client, example):
    r = client.post("/v1/feedback", json=example("feedback"))
    assert r.status_code == 202


def test_trust_disputed(client):
    r = client.get("/v1/trust/svc:passport:fee:normal")
    assert r.status_code == 200
    assert r.json()["status"] == "disputed"


def test_trust_default_ok(client):
    r = client.get("/v1/trust/svc:nic:fee:first_issue")
    assert r.json()["status"] == "ok"
