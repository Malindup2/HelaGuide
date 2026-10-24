"""Read-only dry run: what content schema 3.1 would change for feasibility and for the PP1 checkpoint manifest.

Touches no database, checkpoint, registry or runtime. Models are built in memory only.
Hypothetical rows treat every draft candidate text as if a named reviewer had approved it; nothing is persisted or installed.
"""
import json
import sys
from pathlib import Path

C4 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(C4 / "service"))
from app.learning import lints as policy  # noqa: E402
from app.guidance.content import GuidanceContent  # noqa: E402
from app.guidance.content_v31 import GuidanceContent31, evaluate31  # noqa: E402
from app.guidance.feasibility import evaluate  # noqa: E402
from app.guidance.sources import ProcedureSource  # noqa: E402
from app.procedures.registration import workspace_registry  # noqa: E402

CURRENT = C4 / "research/data/guidance/fictional"
CANDIDATES = C4 / "research/data/guidance/fictional-v31-candidates"
COMBOS = [(e, d) for e in ("concise", "detailed") for d in ("off", "on")]


def counts(candidates):
    out = {f"{e}+{d}": sum(c.feasible for c in candidates if c.configuration.explanation == e and c.configuration.disclosure == d) for e, d in COMBOS}
    out["total"] = sum(c.feasible for c in candidates)
    return out


def main():
    entries, report = workspace_registry(), {"procedures": {}}
    for pid, entry in entries.items():
        source = ProcedureSource(graph=entry["graph"], relationships=entry.get("overlay"))
        current = CURRENT / (pid + ".json")
        c30 = GuidanceContent.model_validate(json.loads(current.read_text(encoding="utf-8"))["content"]) if current.exists() else None
        row = {"content_3_0": counts(evaluate(source, c30))}
        candidate = CANDIDATES / (pid + "-v31.json")
        if candidate.exists():
            c31 = GuidanceContent31.model_validate(json.loads(candidate.read_text(encoding="utf-8"))["content"])
            row["candidate_3_1_as_drafted"] = counts(evaluate31(source, c31))
            row["candidate_3_1_if_reviewed_hypothetical"] = counts(evaluate31(source, c31, assume_reviewed=True))
        else:
            row["candidate_3_1_note"] = "no 3.1 candidate drafted; stays on source fallback (Concise + Disclosure OFF only)"
            row["candidate_3_1_as_drafted"] = counts(evaluate31(source, None))
        report["procedures"][pid] = row
    now, future = policy.manifest(), {**policy.manifest(), "content": "c4-guidance-content-3.1"}
    blob = policy.Model().state()
    try:
        policy.Model.restore(blob, expected=future)
        restore = "accepted"
    except ValueError as error:
        restore = "refused: " + str(error)
    report["checkpoint_manifest"] = {
        "current_content_field": now["content"], "differing_keys_if_content_becomes_3_1": [k for k in now if now[k] != future[k]],
        "restore_of_a_3_0_checkpoint_when_3_1_is_expected": restore,
        "feature_schema_unchanged": now["features"], "feature_fingerprint_unchanged": now["feature_fingerprint"], "action_schema_unchanged": now["action"],
        "note": "Checks used an in-memory model only; no stored checkpoint was opened.",
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
