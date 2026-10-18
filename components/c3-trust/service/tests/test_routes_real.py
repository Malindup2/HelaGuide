"""The HTTP routes in real mode (STUB_MODE=false), backed by the test pipeline."""
import pytest

from app.core.pipeline import set_pipeline
from tests.pipeline_fixtures import ds, pipe, settings  # noqa: F401


@pytest.fixture
def real(monkeypatch, pipe):
    monkeypatch.setenv("STUB_MODE", "false")
    set_pipeline(pipe)
    yield pipe
    set_pipeline(None)


def test_contract_feedback_then_trust(client, real, example):
    r = client.post("/v1/feedback", json=example("feedback"))
    assert r.status_code == 202
    t = client.get("/v1/trust/svc:passport:fee:normal").json()
    assert t["report_count"] == 1 and t["confidence"] < 0.9 and t["status"] == "ok"


def test_unknown_fact_still_answers_so_the_gateway_never_breaks(client, real):
    t = client.get("/v1/trust/svc:nic:fee:ghost").json()
    assert t["status"] == "ok" and t["report_count"] == 0 and t["confidence"] == pytest.approx(0.9)


def test_private_free_text_route_and_explain(client, real, ds):
    r = client.post("/internal/freetext-feedback", json=ds.freetext["ft-A1"])
    assert r.status_code == 200 and r.json()["state"] == "grounded"
    e = client.get("/internal/explain/svc:passport:fee:normal").json()
    assert e["report_count"] == 1 and "warning_code" in e


def test_private_routes_refuse_to_run_in_stub_mode(client, ds, monkeypatch):
    monkeypatch.setenv("STUB_MODE", "true")
    assert client.post("/internal/freetext-feedback", json=ds.freetext["ft-A1"]).status_code == 409
    assert client.get("/internal/explain/svc:passport:fee:normal").status_code == 409


def test_invalid_messages_are_rejected(client, real):
    assert client.post("/v1/feedback", json={"feedback_id": "x"}).status_code == 422
    assert client.post("/internal/freetext-feedback", json={"message_id": "x"}).status_code == 422
