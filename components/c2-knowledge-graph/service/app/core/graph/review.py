"""The review gate: a person approves or rejects each staged fact before it can reach the graph.

Every decision is written to c2.review_log in the same transaction that changes the fact's
status, so the audit trail and the status can never disagree. A fact is decided once:
approving or rejecting something already decided does nothing and says so.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.acquisition.db import PageRegistry

DECISIONS = ("approved", "rejected")


@dataclass
class PendingFact:
    staged_id: int
    fact_id: str
    service_id: str
    predicate: str
    value_text: str
    unit: str | None
    source_url: str
    evidence: str
    old_value: str | None = None  # what the graph holds now for this fact_id, if anything
    forms: list | None = None  # links to forms found beside this fact on the page


class ReviewStore:
    def __init__(self, dsn: str) -> None:
        self.registry = PageRegistry(dsn)
        self.conn = self.registry.conn

    def close(self) -> None:
        self.registry.close()

    def pending(self, service_id: str | None = None, limit: int = 200) -> list[PendingFact]:
        """Pending facts, each with the value currently approved for the same position."""
        rows = self.conn.execute(
            """SELECT s.staged_id, s.fact_id, s.service_id, s.predicate, s.value_text, s.unit,
                      s.source_url, s.evidence,
                      (SELECT p.value_text FROM c2.staged_facts p
                        WHERE p.fact_id = s.fact_id AND p.status = 'approved'
                        ORDER BY p.staged_id DESC LIMIT 1) AS old_value,
                      s.detail -> 'forms' AS forms
               FROM c2.staged_facts s
               WHERE s.status = 'pending' AND (%s::text IS NULL OR s.service_id = %s)
               ORDER BY s.service_id, s.fact_id, s.staged_id
               LIMIT %s""",
            (service_id, service_id, limit),
        ).fetchall()
        return [PendingFact(*r) for r in rows]

    def decide(self, staged_id: int, decision: str, reviewer: str, reason: str = "") -> bool:
        """Record one decision. False when the fact was already decided or does not exist."""
        if decision not in DECISIONS:
            raise ValueError(f"decision must be one of {DECISIONS}")
        if not reviewer.strip():
            raise ValueError("a decision needs a reviewer name for the audit trail")
        with self.conn.transaction():
            row = self.conn.execute(
                """UPDATE c2.staged_facts SET status = %s
                   WHERE staged_id = %s AND status = 'pending' RETURNING fact_id""",
                (decision, staged_id),
            ).fetchone()
            if row is None:
                return False
            self.conn.execute(
                """INSERT INTO c2.review_log (staged_id, fact_id, decision, reason, reviewer)
                   VALUES (%s, %s, %s, %s, %s)""",
                (staged_id, row[0], decision, reason or None, reviewer),
            )
        return True

    def rename_service(self, old: str, new: str, reviewer: str) -> int:
        """Rename the service of the facts still waiting. Decided facts are never touched.

        Used when the model's suggested name for a section is not the name you want. Returns
        how many facts moved; a fact that would collide with one already staged is left alone.
        """
        import re

        if not re.fullmatch(r"svc:[a-z0-9_]+", new):
            raise ValueError("a service id looks like svc:nic_translation (lowercase, digits, _)")
        if old == new:
            return 0
        moved = 0
        with self.conn.transaction():
            rows = self.conn.execute(
                """SELECT staged_id, fact_id FROM c2.staged_facts
                   WHERE status = 'pending' AND service_id = %s""", (old,)).fetchall()
            for staged_id, fact_id in rows:
                if not fact_id.startswith(old + ":"):
                    continue
                new_id = new + fact_id[len(old):]
                clash = self.conn.execute(
                    """SELECT 1 FROM c2.staged_facts WHERE fact_id = %s AND staged_id <> %s
                       AND value_text = (SELECT value_text FROM c2.staged_facts WHERE staged_id = %s)
                       AND source_url = (SELECT source_url FROM c2.staged_facts WHERE staged_id = %s)""",
                    (new_id, staged_id, staged_id, staged_id)).fetchone()
                if clash:
                    continue
                self.conn.execute(
                    """UPDATE c2.staged_facts
                       SET fact_id = %s, service_id = %s,
                           detail = coalesce(detail, '{}'::jsonb)
                                    || jsonb_build_object('renamed_from', %s::text, 'renamed_by', %s::text)
                       WHERE staged_id = %s""", (new_id, new, old, reviewer, staged_id))
                moved += 1
        return moved

    def pending_for_extraction(self, extraction_id: int) -> list[int]:
        return [r[0] for r in self.conn.execute(
            "SELECT staged_id FROM c2.staged_facts WHERE extraction_id = %s AND status = 'pending'",
            (extraction_id,)).fetchall()]

    def latest_extraction_for(self, url: str) -> int | None:
        row = self.conn.execute(
            "SELECT max(extraction_id) FROM c2.extractions WHERE source_url = %s", (url,)).fetchone()
        return row[0] if row else None

    def decide_many(self, staged_ids: list[int], decision: str, reviewer: str,
                    reason: str = "") -> tuple[int, int]:
        """Returns (decided, skipped). Each fact is its own transaction."""
        done = sum(self.decide(i, decision, reviewer, reason) for i in staged_ids)
        return done, len(staged_ids) - done

    def history(self, fact_id: str) -> list[tuple]:
        return self.conn.execute(
            """SELECT decided_at, decision, reviewer, reason, staged_id
               FROM c2.review_log WHERE fact_id = %s ORDER BY decided_at""",
            (fact_id,),
        ).fetchall()

    def counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT status, count(*) FROM c2.staged_facts GROUP BY status"
        ).fetchall()
        return {status: n for status, n in rows}
