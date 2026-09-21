from fastapi import APIRouter, HTTPException, Query, status

from helaguide_common.contracts import SERVICE_ID, Correction, Fact, Plan

from app.core import facts, workflow

router = APIRouter(prefix="/v1", tags=["knowledge-graph"])


@router.get("/plan", response_model=Plan)
async def get_plan(service_id: str = Query(pattern=SERVICE_ID)) -> Plan:
    """Stage 5: the dependency-ordered procedure for one service."""
    plan = workflow.plan_for(service_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown service {service_id}")
    return plan


@router.get("/facts/{fact_id}", response_model=Fact)
async def get_fact(fact_id: str) -> Fact:
    """A fact and its version history. C3 uses this to ground citizen reports."""
    fact = facts.get(fact_id)
    if fact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown fact {fact_id}")
    return fact


@router.post("/corrections", status_code=status.HTTP_202_ACCEPTED)
async def accept_correction(correction: Correction) -> dict:
    """
    A verified correction from C3. Applied as a content-change event, the same
    event class as a value edit found by crawling, so it goes through the
    value-change staleness trigger.
    """
    facts.apply_correction(correction)
    return {"accepted": correction.correction_id}
