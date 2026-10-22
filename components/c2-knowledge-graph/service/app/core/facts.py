"""Fact lookup and correction handling."""
import logging

from helaguide_common.config import get_settings
from helaguide_common.contracts import Correction, Fact, FactVersion
from helaguide_common.examples import load_example

from app.core.graph.driver import get_driver

log = logging.getLogger(__name__)

_QUERY = """
MATCH (f:Fact {fact_id: $fid}) WHERE f.valid_to IS NULL
MATCH (sv:Service)-[:HAS_FACT]->(f)
OPTIONAL MATCH (f)-[:FROM_SOURCE]->(p:SourcePage)
OPTIONAL MATCH (h:Fact {fact_id: $fid}) WHERE h.valid_to IS NOT NULL
RETURN sv.service_id AS service_id, f.predicate AS predicate, f.value AS value,
       f.unit AS unit, p.url AS source_url, f.valid_from AS valid_from,
       collect(DISTINCT {value: h.value, valid_from: h.valid_from, valid_to: h.valid_to}) AS history
"""


def get(fact_id: str) -> Fact | None:
    if get_settings().stub_mode:
        sample = load_example("fact")
        return Fact(**sample) if fact_id == sample["fact_id"] else None

    with get_driver().session() as session:
        row = session.run(_QUERY, fid=fact_id).single()
    if row is None:
        return None
    # neo4j.time.DateTime is not a datetime.datetime -- Pydantic rejects it outright, so
    # every timestamp coming out of the driver must be converted before it reaches a
    # contract model.
    native = lambda t: t.to_native() if t is not None else None  # noqa: E731
    history = [FactVersion(value=h["value"], valid_from=native(h["valid_from"]), valid_to=native(h["valid_to"]))
               for h in row["history"] if h["value"] is not None]
    return Fact(
        fact_id=fact_id,
        service_id=row["service_id"],
        predicate=row["predicate"],
        value=row["value"],
        unit=row["unit"],
        source_url=row["source_url"] or "",
        retrieved_at=native(row["valid_from"]),
        valid_from=native(row["valid_from"]),
        valid_to=None,
        history=history,
    )


def apply_correction(correction: Correction) -> None:
    if get_settings().stub_mode:
        log.info("stub: would apply correction %s to %s", correction.correction_id, correction.fact_id)
        return
    # The content-change path this needs already exists (app.core.graph.writer closes
    # validTo and opens a new version on any changed value). What's missing is only the
    # route from a verified C3 correction into that same path -- not yet wired, since C3's
    # contract for a verified correction isn't exercised against the real graph yet.
    raise NotImplementedError("verified corrections from C3 are not wired to the graph yet")
