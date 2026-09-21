"""
The citizen request path:

    frontend -> gateway -> C1 intent -> C2 plan -> C3 trust -> C4 render -> frontend

Synchronous. No language-model call happens on this path; the heavy work
(crawling, extraction, re-summarisation) runs in C2's background cycle.
"""
import asyncio

import httpx
from fastapi import APIRouter, HTTPException, status

from helaguide_common.contracts import Feedback, Render, UtteranceRequest

from app.clients import services

router = APIRouter(prefix="/v1", tags=["guidance"])


@router.post("/guidance", response_model=Render)
async def guidance(req: UtteranceRequest) -> Render:
    async with httpx.AsyncClient(timeout=services.TIMEOUT) as client:
        try:
            intent = await services.resolve_intent(client, req.session_id, req.text)
            service_id = intent.entities.service_id
            if service_id is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                    "Could not identify a service from that request.")

            plan = await services.get_plan(client, service_id)

            fee_ids = [step.fee.fact_id for step in plan.steps]
            trust = await asyncio.gather(*(services.get_trust(client, f) for f in fee_ids))

            return await services.render(client, req.session_id, plan, list(trust))
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                                f"{exc.request.url.host} returned {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                f"component unreachable: {exc.request.url.host}") from exc


@router.post("/feedback", status_code=status.HTTP_202_ACCEPTED)
async def feedback(body: Feedback) -> dict:
    async with httpx.AsyncClient(timeout=services.TIMEOUT) as client:
        return await services.submit_feedback(client, body)
