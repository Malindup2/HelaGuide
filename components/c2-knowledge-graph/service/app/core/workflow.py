"""Stage 5: reverse prerequisite traversal and topological ordering."""
from helaguide_common.config import get_settings
from helaguide_common.contracts import Plan
from helaguide_common.examples import load_example


def plan_for(service_id: str) -> Plan | None:
    if get_settings().stub_mode:
        sample = load_example("plan")
        if service_id != sample["requested_service_id"]:
            return None
        return Plan(**sample)
    raise NotImplementedError("graph traversal not implemented yet")
