"""Re-process a stored model reply with the current code: no model call, no tokens.

The model's raw reply is kept with every extraction. When the grounding, vocabulary or id rules
improve, the same reply can be run through them again, so a code fix never costs a new call
and the facts always come from exactly what the model said.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.acquisition.discover import strip_menus
from app.core.extraction.extractor import (
    ExtractionResult,
    build_facts,
    build_section_facts,
    parse_extraction,
)
from app.core.extraction.staging import StagingStore


def restage(dsn: str, extraction_id: int, repo_root: Path, dry_run: bool = False,
            service_id: str | None = None):
    """Returns (new_extraction_id or None, facts, dropped, newly staged count).

    service_id files the same reply under a different service: the page was read correctly,
    it was only filed under the wrong service. Ids are rebuilt, so a document that is itself a
    service (an NIC) becomes a prerequisite link of the new service.
    """
    store = StagingStore(dsn)
    try:
        row = store.conn.execute(
            """SELECT source_url, model, raw_reply, source_file, service_id, agency, created_at
               FROM c2.extractions WHERE extraction_id = %s""", (extraction_id,)).fetchone()
        if row is None:
            raise LookupError(f"no extraction {extraction_id}")
        url, model, raw, source_file, stored_service, agency, created = row
        service_id_override = service_id
        service_id = service_id or stored_service
        if not raw or not source_file or not service_id:
            raise LookupError(
                f"extraction {extraction_id} has no stored reply (it ran before replies were kept); "
                "run the extraction once more and it will be re-processable from then on")
        path = Path(source_file)
        path = path if path.is_absolute() else Path(repo_root) / path
        body = strip_menus(path.read_text(encoding="utf-8"))
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and isinstance(parsed.get("services"), list):
            if service_id_override:
                raise LookupError(
                    "this page was read by sections, so each service already has its own name; "
                    "use Rename on the service you want to change instead of filing the page")
            known = frozenset(r[0] for r in store.conn.execute(
                "SELECT DISTINCT service_id FROM c2.staged_facts WHERE status = 'approved' "
                "AND service_id IS NOT NULL"))
            facts, dropped, sections = build_section_facts(parsed, body, url, created.isoformat(),
                                                           known)
            result = ExtractionResult(facts=facts, dropped=dropped, sections=sections,
                                      model=f"{model or 'model'} (re-processed from {extraction_id})",
                                      raw_reply=raw)
        else:
            data, malformed = parse_extraction(parsed)
            facts, dropped = build_facts(data, body, service_id, url, created.isoformat())
            result = ExtractionResult(facts=facts, dropped=malformed + dropped,
                                      model=f"{model or 'model'} (re-processed from {extraction_id})",
                                      raw_reply=raw)
        if dry_run:
            return None, facts, result.dropped, 0
        new_id, staged = store.save(url, result, service_id, agency, source_file=source_file)
        return new_id, facts, result.dropped, staged
    finally:
        store.close()
