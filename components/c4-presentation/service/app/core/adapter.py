"""
C4 research logic. Replace the stub with: read behavioural signals, pick a
support level, compose the steps at the right detail and mode.
"""
from helaguide_common.config import get_settings
from helaguide_common.contracts import Render, RenderRequest, RenderStep


def render(req: RenderRequest) -> Render:
    if not get_settings().stub_mode:
        raise NotImplementedError("adaptive rendering not implemented yet")

    disputed = {t.fact_id for t in req.trust if t.status == "disputed"}
    steps = []
    for s in req.plan.steps:
        fee = "Free" if s.fee.value == 0 else f"{s.fee.currency} {s.fee.value:,.0f}"
        steps.append(RenderStep(
            order=s.order,
            title=s.name,
            body=f"Go to {s.agency}.",
            fee_display=fee,
            documents=[d.name for d in s.documents],
            warning=("Some citizens have reported this fee may have changed."
                     if s.fee.fact_id in disputed else None),
        ))
    return Render(session_id=req.session_id, plan_id=req.plan.plan_id,
                  mode="standard", detail_level="medium", steps=steps)
