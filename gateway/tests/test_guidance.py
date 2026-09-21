"""
Exercises the full request path with every component mocked by its contract
example, so the gateway can be tested without anything else running.
"""
import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from helaguide_common.config import get_settings
from helaguide_common.examples import load_example

from app.main import app

S = get_settings()


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


@respx.mock
def test_guidance_end_to_end(client):
    respx.post(f"{S.c1_url}/v1/intent").mock(return_value=httpx.Response(200, json=load_example("intent")))
    respx.get(f"{S.c2_url}/v1/plan").mock(return_value=httpx.Response(200, json=load_example("plan")))
    respx.get(url__startswith=f"{S.c3_url}/v1/trust/").mock(return_value=httpx.Response(200, json=load_example("trust")))
    respx.post(f"{S.c4_url}/v1/render").mock(return_value=httpx.Response(200, json=load_example("render")))

    r = client.post("/v1/guidance", json={"session_id": "anon-7f3c", "text": "passport ekak ganna one"})
    assert r.status_code == 200
    assert len(r.json()["steps"]) == 2


@respx.mock
def test_guidance_component_down(client):
    respx.post(f"{S.c1_url}/v1/intent").mock(side_effect=httpx.ConnectError("down"))
    r = client.post("/v1/guidance", json={"session_id": "anon-7f3c", "text": "passport"})
    assert r.status_code == 503
