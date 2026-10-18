import pytest


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


# ------------------------------------------------------- real mode, over real HTTP
def test_plan_served_over_http_against_the_real_graph(monkeypatch):
    from pathlib import Path

    from fastapi.testclient import TestClient

    from app.core.graph.writer import neo4j_from_dotenv

    repo_root = Path(__file__).resolve().parents[4]
    conf = neo4j_from_dotenv(repo_root / ".env")
    if conf is None:
        pytest.skip("no .env with NEO4J_* settings")
    uri, user, password = conf
    monkeypatch.setenv("NEO4J_URI", uri)
    monkeypatch.setenv("NEO4J_USER", user)
    monkeypatch.setenv("NEO4J_PASSWORD", password)
    monkeypatch.setenv("STUB_MODE", "false")
    from app.core.graph.driver import get_driver
    get_driver.cache_clear()
    try:
        get_driver().verify_connectivity()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Neo4j is not reachable: {type(e).__name__}")

    from app.main import app
    real_client = TestClient(app)
    r = real_client.get("/v1/plan", params={"service_id": "svc:passport"})
    assert r.status_code == 200
    body = r.json()
    assert body["requested_service_id"] == "svc:passport"
    ids = [s["service_id"] for s in body["steps"]]
    assert ids.index("svc:nic") < ids.index("svc:passport")
    get_driver.cache_clear()
