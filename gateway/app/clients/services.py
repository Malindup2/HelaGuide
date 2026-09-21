"""
HTTP clients for the four components. The gateway is the only place that knows
where they live; the frontend only ever knows the gateway.
"""
import httpx

from helaguide_common.config import get_settings
from helaguide_common.contracts import Feedback, Intent, Plan, Render, TrustScore

TIMEOUT = httpx.Timeout(10.0)


def _urls():
    s = get_settings()
    return {"c1": s.c1_url, "c2": s.c2_url, "c3": s.c3_url, "c4": s.c4_url}


async def resolve_intent(client: httpx.AsyncClient, session_id: str, text: str) -> Intent:
    r = await client.post(f"{_urls()['c1']}/v1/intent", json={"session_id": session_id, "text": text})
    r.raise_for_status()
    return Intent(**r.json())


async def get_plan(client: httpx.AsyncClient, service_id: str) -> Plan:
    r = await client.get(f"{_urls()['c2']}/v1/plan", params={"service_id": service_id})
    r.raise_for_status()
    return Plan(**r.json())


async def get_trust(client: httpx.AsyncClient, fact_id: str) -> TrustScore:
    r = await client.get(f"{_urls()['c3']}/v1/trust/{fact_id}")
    r.raise_for_status()
    return TrustScore(**r.json())


async def render(client: httpx.AsyncClient, session_id: str, plan: Plan,
                 trust: list[TrustScore]) -> Render:
    body = {"session_id": session_id,
            "plan": plan.model_dump(mode="json"),
            "trust": [t.model_dump(mode="json") for t in trust]}
    r = await client.post(f"{_urls()['c4']}/v1/render", json=body)
    r.raise_for_status()
    return Render(**r.json())


async def submit_feedback(client: httpx.AsyncClient, feedback: Feedback) -> dict:
    r = await client.post(f"{_urls()['c3']}/v1/feedback", json=feedback.model_dump(mode="json"))
    r.raise_for_status()
    return r.json()


async def health(client: httpx.AsyncClient) -> dict:
    out = {}
    for name, url in _urls().items():
        try:
            r = await client.get(f"{url}/health", timeout=2.0)
            out[name] = "ok" if r.status_code == 200 else f"http {r.status_code}"
        except httpx.HTTPError as exc:
            out[name] = f"unreachable ({type(exc).__name__})"
    return out
