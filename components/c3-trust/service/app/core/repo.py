"""Every database read and write C3 makes goes through this class."""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Iterable

import numpy as np
from sqlalchemy import and_, delete, func, insert, select, update
from sqlalchemy.engine import Engine

from app.core import db
from app.core.util import as_utc, parse_date
from app.models.internal import ConfidenceRecord, FactVersion, ReportRow, Reporter


def _emb_to_bytes(e) -> bytes | None:
    return None if e is None else np.asarray(e, dtype=np.float32).tobytes()


def _bytes_to_emb(b) -> np.ndarray | None:
    return None if b is None else np.frombuffer(bytes(b), dtype=np.float32).copy()


class Repo:
    def __init__(self, engine: Engine):
        self.engine = engine

    # ------------------------------------------------------------- facts ---
    def _fact_from_row(self, r) -> FactVersion:
        return FactVersion(
            fact_id=r.fact_id, service_id=r.service_id, predicate=r.predicate, qualifier=r.qualifier,
            value_text=r.value_text, value_num=r.value_num, unit=r.unit, description=r.description or "",
            source_url=r.source_url, retrieved_at=as_utc(r.retrieved_at),
            valid_from=as_utc(r.valid_from), valid_to=as_utc(r.valid_to),
            connection_unverified=bool(r.connection_unverified), embedding=_bytes_to_emb(r.embedding))

    def get_version(self, fact_id: str, valid_from: datetime) -> FactVersion | None:
        t = db.fact_registry
        with self.engine.connect() as c:
            for r in c.execute(select(t).where(t.c.fact_id == fact_id)):
                if as_utc(r.valid_from) == as_utc(valid_from):
                    return self._fact_from_row(r)
        return None

    def versions(self, fact_id: str) -> list[FactVersion]:
        t = db.fact_registry
        with self.engine.connect() as c:
            rows = [self._fact_from_row(r) for r in c.execute(select(t).where(t.c.fact_id == fact_id))]
        return sorted(rows, key=lambda f: f.valid_from)

    def current_version(self, fact_id: str) -> FactVersion | None:
        vs = [v for v in self.versions(fact_id) if v.valid_to is None]
        return vs[-1] if vs else None

    def version_at(self, fact_id: str, when: datetime) -> FactVersion | None:
        when = as_utc(when)
        vs = self.versions(fact_id)
        hit = [v for v in vs if v.valid_from <= when and (v.valid_to is None or when < v.valid_to)]
        if hit:
            return hit[-1]
        return vs[0] if vs and when < vs[0].valid_from else (vs[-1] if vs else None)

    def list_current_facts(self) -> list[FactVersion]:
        t = db.fact_registry
        with self.engine.connect() as c:
            rows = c.execute(select(t).where(t.c.valid_to.is_(None))).fetchall()
        return [self._fact_from_row(r) for r in rows]

    def insert_version(self, f: FactVersion) -> None:
        with self.engine.begin() as c:
            c.execute(insert(db.fact_registry).values(
                fact_id=f.fact_id, valid_from=f.valid_from, valid_to=f.valid_to,
                service_id=f.service_id, predicate=f.predicate, qualifier=f.qualifier,
                value_text=f.value_text, value_num=f.value_num, unit=f.unit,
                description=f.description, source_url=f.source_url, retrieved_at=f.retrieved_at,
                connection_unverified=f.connection_unverified, embedding=_emb_to_bytes(f.embedding)))

    def close_version(self, fact_id: str, valid_from: datetime, valid_to: datetime) -> None:
        t = db.fact_registry
        with self.engine.begin() as c:
            c.execute(update(t).where(and_(t.c.fact_id == fact_id, t.c.valid_from == valid_from))
                      .values(valid_to=valid_to))

    # -------------------------------------------------------- confidence ---
    def _conf_from_row(self, r) -> ConfidenceRecord:
        return ConfidenceRecord(
            fact_id=r.fact_id, valid_from=as_utc(r.valid_from), base_confidence=r.base_confidence,
            confidence=r.confidence, status=r.status, drop_events=r.drop_events,
            verified_by_source=bool(r.verified_by_source), last_updated=as_utc(r.last_updated),
            last_reason=r.last_reason)

    def get_confidence(self, fact_id: str, valid_from: datetime) -> ConfidenceRecord | None:
        t = db.fact_confidence
        with self.engine.connect() as c:
            for r in c.execute(select(t).where(t.c.fact_id == fact_id)):
                if as_utc(r.valid_from) == as_utc(valid_from):
                    return self._conf_from_row(r)
        return None

    def insert_confidence(self, rec: ConfidenceRecord) -> None:
        with self.engine.begin() as c:
            c.execute(insert(db.fact_confidence).values(
                fact_id=rec.fact_id, valid_from=rec.valid_from, base_confidence=rec.base_confidence,
                confidence=rec.confidence, status=rec.status, drop_events=rec.drop_events,
                verified_by_source=rec.verified_by_source, last_updated=rec.last_updated,
                last_reason=rec.last_reason))

    def save_confidence(self, rec: ConfidenceRecord) -> None:
        t = db.fact_confidence
        with self.engine.begin() as c:
            c.execute(update(t).where(and_(t.c.fact_id == rec.fact_id, t.c.valid_from == rec.valid_from))
                      .values(confidence=rec.confidence, status=rec.status, drop_events=rec.drop_events,
                              verified_by_source=rec.verified_by_source, last_updated=rec.last_updated,
                              last_reason=rec.last_reason))

    def add_audit(self, fact_id: str, valid_from: datetime, old: float | None, new: float,
                  reason: str, report_ids: list[str], when: datetime) -> None:
        with self.engine.begin() as c:
            c.execute(insert(db.confidence_audit).values(
                fact_id=fact_id, valid_from=valid_from, old_confidence=old, new_confidence=new,
                reason=reason, report_ids=report_ids, created_at=when))

    def audit_rows(self, fact_id: str, valid_from: datetime | None = None) -> list[dict]:
        t = db.confidence_audit
        with self.engine.connect() as c:
            rows = c.execute(select(t).where(t.c.fact_id == fact_id).order_by(t.c.audit_id)).fetchall()
        out = []
        for r in rows:
            if valid_from is None or as_utc(r.valid_from) == as_utc(valid_from):
                out.append({"old": r.old_confidence, "new": r.new_confidence, "reason": r.reason,
                            "report_ids": r.report_ids, "at": as_utc(r.created_at)})
        return out

    # --------------------------------------------------------- reporters ---
    def _rep_from_row(self, r) -> Reporter:
        return Reporter(reporter_id=r.reporter_id, created_at=as_utc(r.created_at), a=r.a, b=r.b,
                        rep_day=parse_date(r.rep_day), rep_delta_today=r.rep_delta_today or 0.0)

    def get_reporter(self, reporter_id: str) -> Reporter | None:
        t = db.reporters
        with self.engine.connect() as c:
            r = c.execute(select(t).where(t.c.reporter_id == reporter_id)).first()
        return self._rep_from_row(r) if r else None

    def ensure_reporter(self, reporter_id: str, first_seen: datetime) -> Reporter:
        rep = self.get_reporter(reporter_id)
        if rep:
            return rep
        with self.engine.begin() as c:
            c.execute(insert(db.reporters).values(reporter_id=reporter_id, created_at=first_seen,
                                                  a=0.0, b=0.0, rep_delta_today=0.0))
        return self.get_reporter(reporter_id)  # type: ignore[return-value]

    def upsert_reporter(self, rep: Reporter) -> None:
        existing = self.get_reporter(rep.reporter_id)
        with self.engine.begin() as c:
            if existing:
                c.execute(update(db.reporters).where(db.reporters.c.reporter_id == rep.reporter_id)
                          .values(created_at=rep.created_at, a=rep.a, b=rep.b))
            else:
                c.execute(insert(db.reporters).values(reporter_id=rep.reporter_id, created_at=rep.created_at,
                                                      a=rep.a, b=rep.b, rep_delta_today=0.0))

    def apply_reputation(self, reporter_id: str, da: float, dbad: float, day: date, delta_max: float) -> tuple[float, float]:
        """Add to a (right) and b (wrong), but never move a reporter by more than delta_max per day."""
        rep = self.get_reporter(reporter_id)
        if rep is None:
            return 0.0, 0.0
        used = rep.rep_delta_today if rep.rep_day == day else 0.0
        room = max(0.0, delta_max - used)
        total = da + dbad
        scale = 1.0 if total <= room or total == 0 else room / total
        da2, db2 = da * scale, dbad * scale
        with self.engine.begin() as c:
            c.execute(update(db.reporters).where(db.reporters.c.reporter_id == reporter_id)
                      .values(a=rep.a + da2, b=rep.b + db2, rep_day=day, rep_delta_today=used + da2 + db2))
        return da2, db2

    def all_reporters(self) -> list[Reporter]:
        with self.engine.connect() as c:
            return [self._rep_from_row(r) for r in c.execute(select(db.reporters).order_by(db.reporters.c.reporter_id))]

    # ----------------------------------------------------------- reports ---
    def _report_from_row(self, r) -> ReportRow:
        return ReportRow(
            report_id=r.report_id, message_id=r.message_id, path=r.path, reporter_id=r.reporter_id,
            raw_text=r.raw_text, text_en=r.text_en, language=r.language, fact_id=r.fact_id,
            fact_valid_from=as_utc(r.fact_valid_from), discrepancy_type=r.discrepancy_type or "",
            report_kind=r.report_kind, claimed_value_raw=r.claimed_value_raw, claimed_num=r.claimed_num,
            claimed_key=r.claimed_key or "unspecified", visit_date=parse_date(r.visit_date),
            submitted_at=as_utc(r.submitted_at), trust_t=r.trust_t, sig_r=r.sig_r, sig_s=r.sig_s,
            sig_c=r.sig_c, sig_v=r.sig_v, v_imputed=bool(r.v_imputed), dup_count=r.dup_count or 0,
            indep_i=r.indep_i if r.indep_i is not None else 1.0, state=r.state,
            embedding=_bytes_to_emb(r.embedding), trace=r.trace or {})

    def get_report_by_message(self, message_id: str) -> ReportRow | None:
        t = db.reports
        with self.engine.connect() as c:
            r = c.execute(select(t).where(t.c.message_id == message_id)).first()
        return self._report_from_row(r) if r else None

    def get_unresolved_by_message(self, message_id: str) -> dict | None:
        t = db.unresolved_reports
        with self.engine.connect() as c:
            r = c.execute(select(t).where(t.c.message_id == message_id)).first()
        return None if r is None else {"report_id": r.report_id, "state": r.state, "reason": r.reason}

    def insert_report(self, row: ReportRow) -> None:
        with self.engine.begin() as c:
            c.execute(insert(db.reports).values(
                report_id=row.report_id, message_id=row.message_id, path=row.path, reporter_id=row.reporter_id,
                raw_text=row.raw_text, text_en=row.text_en, language=row.language, fact_id=row.fact_id,
                fact_valid_from=row.fact_valid_from, discrepancy_type=row.discrepancy_type,
                report_kind=row.report_kind, claimed_value_raw=row.claimed_value_raw, claimed_num=row.claimed_num,
                claimed_key=row.claimed_key, visit_date=row.visit_date, submitted_at=row.submitted_at,
                trust_t=row.trust_t, sig_r=row.sig_r, sig_s=row.sig_s, sig_c=row.sig_c, sig_v=row.sig_v,
                v_imputed=row.v_imputed, dup_count=row.dup_count, indep_i=row.indep_i, state=row.state,
                embedding=_emb_to_bytes(row.embedding), trace=json.loads(json.dumps(row.trace, default=str))))

    def reports_for(self, fact_id: str, valid_from: datetime, states: Iterable[str] | None = None) -> list[ReportRow]:
        t = db.reports
        with self.engine.connect() as c:
            rows = c.execute(select(t).where(t.c.fact_id == fact_id)).fetchall()
        out = [self._report_from_row(r) for r in rows if as_utc(r.fact_valid_from) == as_utc(valid_from)]
        if states is not None:
            states = set(states)
            out = [r for r in out if r.state in states]
        return sorted(out, key=lambda r: (r.submitted_at, r.message_id))

    def set_report_state(self, report_id: str, state: str) -> None:
        with self.engine.begin() as c:
            c.execute(update(db.reports).where(db.reports.c.report_id == report_id).values(state=state))

    def count_reports(self) -> int:
        with self.engine.connect() as c:
            return c.execute(select(func.count()).select_from(db.reports)).scalar_one()

    # -------------------------------------------------------- unresolved ---
    def insert_unresolved(self, report_id: str, message_id: str, path: str, reporter_id: str, raw_text: str,
                          text_en: str | None, service_id: str | None, predicate: str | None, state: str,
                          reason: str, trace: dict, when: datetime) -> None:
        with self.engine.begin() as c:
            c.execute(insert(db.unresolved_reports).values(
                report_id=report_id, message_id=message_id, path=path, reporter_id=reporter_id,
                raw_text=raw_text, text_en=text_en, service_id=service_id, predicate=predicate,
                state=state, reason=reason, trace=json.loads(json.dumps(trace, default=str)), created_at=when))

    def list_unresolved(self) -> list[dict]:
        t = db.unresolved_reports
        with self.engine.connect() as c:
            return [dict(r._mapping) for r in c.execute(select(t).order_by(t.c.created_at))]

    # ---------------------------------------------------------- sessions ---
    def get_session_service(self, session_id: str) -> str | None:
        t = db.sessions
        with self.engine.connect() as c:
            r = c.execute(select(t).where(t.c.session_id == session_id)).first()
        return r.last_service_id if r else None

    def set_session_service(self, session_id: str, service_id: str, when: datetime) -> None:
        t = db.sessions
        with self.engine.begin() as c:
            exists = c.execute(select(t.c.session_id).where(t.c.session_id == session_id)).first()
            if exists:
                c.execute(update(t).where(t.c.session_id == session_id)
                          .values(last_service_id=service_id, updated_at=when))
            else:
                c.execute(insert(t).values(session_id=session_id, last_service_id=service_id, updated_at=when))
