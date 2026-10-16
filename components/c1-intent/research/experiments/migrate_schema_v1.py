r"""
Migrate seed dialogues from schema v0 to v1.

Merges the six services outside the Knowledge Graph's scope into
'unsupported_service'. Edits data/seed_dialogues_*.json IN PLACE,
so any fixes you already made (e.g. kohenda -> koheda) are kept.
A backup of each file is saved to data/backup_v0/ first.

Run from components/c1-intent/research/:
    conda activate nlp
    python experiments\migrate_schema_v1.py
"""
import glob
import json
import shutil
from collections import Counter
from pathlib import Path

DATA = Path("data")

UNSUPPORTED = {
    "driving_license":       "driving license",
    "police_clearance":      "police clearance",
    "business_register":     "business registration",
    "building_permit":       "building permit",
    "utility_connection":    "utility connection",
    "residence_certificate": "residence certificate",
}


def migrate_state(state: dict) -> bool:
    """Returns True if the state was changed."""
    changed = False
    old = state.get("intent")
    if old in UNSUPPORTED:
        state["original_intent"] = old           # kept so it can be restored later
        state["original_slots"] = state.get("slots", {})
        state["intent"] = "unsupported_service"
        state["slots"] = {"service_mentioned": UNSUPPORTED[old]}
        changed = True
    prev = state.get("previous_intent")
    if prev in UNSUPPORTED:
        state["previous_intent"] = "unsupported_service"
        changed = True
    # An intent switch between two unsupported services is no longer a switch.
    if state.get("previous_intent") == state.get("intent") == "unsupported_service":
        del state["previous_intent"]
    return changed


def main():
    backup = DATA / "backup_v0"
    backup.mkdir(exist_ok=True)
    files = sorted(glob.glob(str(DATA / "seed_dialogues_*.json")))
    if not files:
        print("No data/seed_dialogues_*.json found. Run this from the project folder.")
        return

    turns_changed, intents = 0, Counter()
    for f in files:
        if not (backup / Path(f).name).exists():
            shutil.copy(f, backup / Path(f).name)
        with open(f, encoding="utf-8") as fh:
            dialogues = json.load(fh)
        for d in dialogues:
            for t in d["turns"]:
                if "state" in t and migrate_state(t["state"]):
                    turns_changed += 1
            first = next(t for t in d["turns"] if t["speaker"] == "user")
            intents[first["state"]["intent"]] += 1
            if any(t.get("state", {}).get("intent") == "unsupported_service" for t in d["turns"]):
                d["route"] = "fallback"
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(dialogues, fh, ensure_ascii=False, indent=2)

    print(f"Updated {turns_changed} user turns across {len(files)} files (backup in data/backup_v0/)")
    print("Dialogues per starting intent:")
    for k, v in sorted(intents.items(), key=lambda x: -x[1]):
        print(f"  {k:24s}{v}")


if __name__ == "__main__":
    main()
