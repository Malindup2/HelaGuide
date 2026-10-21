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
        for entry in self.procedures.values():
            if entry["preparation"]["missing"]:
                queue_preparation(entry, Path(path).parent/"preparation")

mode=os.getenv("C4_WORKSPACE_MODE", "simulation")
path=os.getenv("C4_WORKSPACE_DATABASE") or Path(__file__).resolve().parents[1]/".local"/"v2"/"workspace"/mode/"state.sqlite3"
content_mode = os.getenv("C4_WORKSPACE_CONTENT_MODE", "demo")
if content_mode not in ("demo", "prepare"):
    raise ValueError("C4_WORKSPACE_CONTENT_MODE must be demo or prepare")
llm_enabled = os.getenv("C4_LLM_ENABLED", "false").lower()
if llm_enabled not in ("true", "false"):
    raise ValueError("C4_LLM_ENABLED must be true or false")

def provider_factory():
    from app.core.llm_provider import OpenAIExplanationProvider
    return OpenAIExplanationProvider.from_environment()

app=create_app(path, mode=mode, seed=int(os.getenv("C4_WORKSPACE_SEED", "0")), runtime_class=ActiveRuntime, workspace=True,
    preparation_options={"enabled":content_mode == "prepare" and llm_enabled == "true", "provider_factory":provider_factory})
