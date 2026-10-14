"""
Helpers that run grounding WITHOUT touching the database, for the demo and the tuning tool.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.core.config import C3Settings
from app.core.pipeline import Pipeline
from app.core.util import parse_dt


@dataclass
class Loaded:
    freetext: dict[str, dict]
    structured: dict[str, dict]
    extras: dict[str, dict]
    labels: list[dict]

    def when(self, label: dict) -> datetime:
        m = self.freetext.get(label["message_id"]) or self.structured[label["message_id"]]
        return parse_dt(m.get("timestamp") or m["submitted_at"])

    def ordered(self) -> list[dict]:
        return sorted(self.labels, key=lambda l: (self.when(l), l["message_id"]))


def load_dataset(data_dir: Path) -> Loaded:
    rd = lambda n: json.loads((Path(data_dir) / n).read_text(encoding="utf-8"))
    return Loaded(
        freetext={m["message_id"]: m for m in rd("feedback_freetext.json")["messages"]},
        structured={m["feedback_id"]: m for m in rd("feedback_structured.json")["messages"]},
        extras=rd("structured_extras.json")["extras"],
        labels=rd("expected_labels.json")["labels"])


def ground_only(pipe: Pipeline, ds: Loaded, label: dict, sessions: dict[str, str]) -> dict:
    """Normalise + ground one labelled message. `sessions` emulates the per-session memory."""
    mid = label["message_id"]
    if mid in ds.freetext:
        m = ds.freetext[mid]
        e = m["entities"]
        norm = pipe.normaliser.normalise(m["raw_text"], m.get("language"), m.get("text_en"))
        g = pipe.grounding.ground_text(
            norm.text_en, m["raw_text"], service_hint=e.get("service_id"), predicate_hint=e.get("predicate_hint"),
            session_service=sessions.get(m["session_id"]), when=parse_dt(m["timestamp"]))
        sid = m["session_id"]
        raw = m["raw_text"]
    else:
        m = ds.structured[mid]
        norm = pipe.normaliser.normalise(m["text"], None, None)
        g = pipe.grounding.ground_structured(m["fact_id"], parse_dt(m["submitted_at"]))
        sid, raw = m["session_id"], m["text"]
    if g.service_id:
        sessions[sid] = g.service_id
    ok = g.state == label["expected_state"] and (
        g.state != "grounded" or g.fact_id == label["expected_fact_id"])
    return {"label": label, "raw_text": raw, "text_en": norm.text_en, "backend": norm.backend, "result": g, "ok": ok}


def run_grounding(pipe: Pipeline, ds: Loaded, only_ids: set[str] | None = None) -> list[dict]:
    sessions: dict[str, str] = {}
    rows = []
    for label in ds.ordered():
        row = ground_only(pipe, ds, label, sessions)
        if only_ids is None or label["message_id"] in only_ids:
            rows.append(row)
    return rows


def accuracy_by(rows: list[dict], key: str) -> dict[str, tuple[int, int]]:
    out: dict[str, list[int]] = {}
    for r in rows:
        out.setdefault(r["label"][key], []).append(1 if r["ok"] else 0)
    return {k: (sum(v), len(v)) for k, v in out.items()}
