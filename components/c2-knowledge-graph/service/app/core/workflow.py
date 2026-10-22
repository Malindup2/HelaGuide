"""Stage 5: reverse prerequisite traversal and topological ordering.

Real mode walks the live Neo4j graph (app.core.graph.plan.build_plan, no language model)
and reshapes the result into the shared contract. One simplification, worth stating plainly:
the contract's PlanStep carries a single Fee, but a service in the real graph often has
several (first issue, lost, one-day...). Until the contract is extended to a list -- the
decision PLAN.md names as still open with the team -- this picks one fee per step by a fixed
preference order, documented in _pick_fee below, rather than inventing an average or
dropping the field.
"""
from __future__ import annotations

from datetime import datetime, timezone

from helaguide_common.config import get_settings
from helaguide_common.contracts import Document, Fee, Plan, PlanStep, Provenance
from helaguide_common.examples import load_example

from app.core.graph import plan as graph_plan
from app.core.graph.driver import get_driver

# Checked in order, most specific first: "standard" alone would match "amended_standard"
# before "first_issue_standard" simply because it comes first in the fact list, which is
# the wrong fee for a first-time applicant. first_issue must be tried before the generic
# standard/normal/ordinary fallbacks.
_PREFERRED_QUALIFIERS = ("first_issue", "ordinary_normal", "ordinary", "normal", "standard")


def _pick_fee(fees: list[graph_plan.Item]) -> graph_plan.Item | None:
    """One fee per step, preferring a qualifier that reads as the common case."""
    priced = [f for f in fees if f.amount is not None]
    if not priced:
        return None
    for want in _PREFERRED_QUALIFIERS:
        for f in priced:
            if want in (f.qualifier or ""):
                return f
    return priced[0]


def _to_plan_step(step: graph_plan.Step) -> tuple[PlanStep, dict[str, Provenance]]:
    provenance: dict[str, Provenance] = {}

    def note(item: graph_plan.Item) -> None:
        if item.source_url:
            provenance[item.fact_id] = Provenance(
                source_url=item.source_url, retrieved_at=datetime.now(timezone.utc))

    fee_item = _pick_fee(step.fees)
    for f in step.fees:
        note(f)
    fee = (Fee(value=fee_item.amount, currency=fee_item.unit or "LKR", fact_id=fee_item.fact_id)
           if fee_item else Fee(value=0.0, currency="LKR", fact_id=f"{step.service_id}:fee:unknown"))

    documents: list[Document] = []
    for d in step.documents:
        note(d)
        documents.append(Document(name=d.value, fact_id=d.fact_id))

    return PlanStep(
        order=step.order,
        service_id=step.service_id,
        name=step.service_id.removeprefix("svc:").replace("_", " "),
        agency=step.agency or "unknown",
        fee=fee,
        documents=documents,
        depends_on=step.depends_on,
    ), provenance


def plan_for(service_id: str, case: str | None = None) -> Plan | None:
    if get_settings().stub_mode:
        sample = load_example("plan")
        if service_id != sample["requested_service_id"]:
            return None
        return Plan(**sample)

    raw = graph_plan.build_plan(get_driver(), service_id, case)
    if raw is None:
        return None
    # A cycle would mean no valid order exists (FR14): report it as "not found" rather
    # than serve a plan that silently omits the step that completes the cycle.
    if raw.cycle:
        return None

    steps: list[PlanStep] = []
    provenance: dict[str, Provenance] = {}
    for s in raw.steps:
        step, prov = _to_plan_step(s)
        steps.append(step)
        provenance.update(prov)

    return Plan(
        plan_id=f"plan:{service_id}:{int(datetime.now(timezone.utc).timestamp())}",
        requested_service_id=service_id,
        generated_at=datetime.now(timezone.utc),
        steps=steps,
        provenance=provenance,
    )
