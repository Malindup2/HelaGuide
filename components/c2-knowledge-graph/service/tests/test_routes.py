def test_plan_stub(client):
    r = client.get("/v1/plan", params={"service_id": "svc:passport"})
    assert r.status_code == 200
    steps = r.json()["steps"]
    assert [s["order"] for s in steps] == sorted(s["order"] for s in steps)


def test_plan_unknown_service(client):
    assert client.get("/v1/plan", params={"service_id": "svc:unknown"}).status_code == 404


def test_plan_rejects_bad_id(client):
    assert client.get("/v1/plan", params={"service_id": "passport"}).status_code == 422


def test_fact_stub(client):
    r = client.get("/v1/facts/svc:passport:fee:normal")
    assert r.status_code == 200
    assert r.json()["valid_to"] is None


def test_correction_accepted(client, example):
    r = client.post("/v1/corrections", json=example("correction"))
    assert r.status_code == 202
