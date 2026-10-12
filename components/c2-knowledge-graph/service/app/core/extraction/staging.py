"""Staged facts in PostgreSQL (c2.extractions, c2.staged_facts). Schema: 003_c2_extraction.sql."""

from __future__ import annotations

import json
from datetime import datetime

from app.core.acquisition.db import PageRegistry
from app.core.extraction.extractor import ExtractionResult


class StagingStore:
    def __init__(self, dsn: str) -> None:
        self.registry = PageRegistry(dsn)
        self.conn = self.registry.conn

    def close(self) -> None:
        self.registry.close()

    def save(self, source_url: str, result: ExtractionResult, service_id: str | None = None,
             agency: str | None = None, source_file: str | None = None) -> tuple[int, int]:
        """Record one extraction and its facts. Returns (extraction_id, new facts staged).

        A fact already staged with the same id, value and source is skipped, so extracting an
        unchanged page twice does not fill the review queue with duplicates.
        """
        page_id = self.registry.page_id(source_url, service_id, agency)
        extraction_id = self.conn.execute(
            """INSERT INTO c2.extractions
                   (page_id, source_url, model, prompt_tokens, completion_tokens, facts, dropped,
                    truncated, error, raw_reply, source_file, service_id, agency)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING extraction_id""",
            (page_id, source_url, result.model or None, result.prompt_tokens,
             result.completion_tokens, len(result.facts), len(result.dropped), result.truncated,
             result.error or None, result.raw_reply or None, source_file, service_id, agency),
        ).fetchone()[0]

        staged = 0
        for f in result.facts:
            row = self.conn.execute(
                """INSERT INTO c2.staged_facts
                       (extraction_id, fact_id, service_id, predicate, qualifier, value_text,
                        value_num, unit, detail, source_url, retrieved_at, evidence, status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (fact_id, value_text, source_url) DO NOTHING
                   RETURNING staged_id""",
                (extraction_id, f.fact_id, f.service_id, f.predicate, f.qualifier, f.value_text,
                 f.value_num, f.unit, json.dumps(f.detail), f.source_url,
                 datetime.fromisoformat(f.retrieved_at), f.evidence, f.status),
            ).fetchone()
            staged += 1 if row else 0
        return extraction_id, staged

    def pending(self) -> list[tuple]:
        return self.conn.execute(
            """SELECT fact_id, value_text, unit, source_url FROM c2.staged_facts
               WHERE status = 'pending' ORDER BY fact_id"""
        ).fetchall()
