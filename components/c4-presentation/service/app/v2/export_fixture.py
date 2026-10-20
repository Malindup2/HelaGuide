"""Export a real selected V2 journey for cross-language renderer contract tests."""
import json
from pathlib import Path
from app.v2.runtime import Runtime
from app.v2.catalogue import Context
runtime=Runtime(seed=19)
journey=runtime.create("synthetic-practice-v2",Context(familiarity=1,confidence=1),"renderer-fixture-v2")
journey.pop("token")
path=Path(__file__).resolve().parents[3]/"demo-frontend/src/guidance-v2/fixture.json"
path.write_text(json.dumps(journey,indent=2),encoding="utf-8")
runtime.close()
