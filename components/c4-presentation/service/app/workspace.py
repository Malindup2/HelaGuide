"""Unified C4 application: V1 citizen identity, V2 policy and scaffolding.

Run app.workspace:app. Historical app.dev_main and app.v2.api remain available
for reproducing isolated baseline experiments, not competing citizen routes.
"""
import os
from pathlib import Path
from app.v2.api import create_app
from app.v2.identity import WorkspaceRuntime
from app.v2.registration import workspace_registry, queue_preparation

class ActiveRuntime(WorkspaceRuntime):
    def __init__(self, path, **kwargs):
        entries=workspace_registry()
        super().__init__(path, procedures=entries, **kwargs)
        for entry in entries.values():
            if entry["preparation"]["missing"]:
                queue_preparation(entry, Path(path).parent/"preparation")

mode=os.getenv("C4_WORKSPACE_MODE", "simulation")
path=os.getenv("C4_WORKSPACE_DATABASE") or Path(__file__).resolve().parents[1]/".local"/"v2"/"workspace"/mode/"state.sqlite3"
app=create_app(path, mode=mode, seed=int(os.getenv("C4_WORKSPACE_SEED", "0")), runtime_class=ActiveRuntime, workspace=True)
