def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["service"] == "c1-intent"
