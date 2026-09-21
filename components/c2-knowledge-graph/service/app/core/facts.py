"""Fact lookup and correction handling."""
import logging

from helaguide_common.config import get_settings
from helaguide_common.contracts import Correction, Fact
from helaguide_common.examples import load_example

log = logging.getLogger(__name__)


def get(fact_id: str) -> Fact | None:
    if get_settings().stub_mode:
        sample = load_example("fact")
        return Fact(**sample) if fact_id == sample["fact_id"] else None
    raise NotImplementedError("Neo4j lookup not implemented yet")


def apply_correction(correction: Correction) -> None:
    if get_settings().stub_mode:
        log.info("stub: would apply correction %s to %s", correction.correction_id, correction.fact_id)
        return
    raise NotImplementedError("correction handling not implemented yet")
