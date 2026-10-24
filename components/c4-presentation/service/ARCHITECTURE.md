# C4 V3.1 backend architecture

Run the live application with `uvicorn app.workspace:app --env-file .env --host 127.0.0.1 --port 8021` (unchanged).
The team Docker entry is still `app.main:app` (port 8004, C2 `Plan` render stub) and the historical V1 server is
still `app.dev_main:app`.

## Packages (`service/app/`)
| Package | Role | Imported by the live app |
|---|---|---|
| `workspace.py` | Entry point: reads `C4_*` settings, builds the app | yes (entry) |
| `host/` | FastAPI factory (`application.py`), workspace and `/dev/v1/*` routes (`routes.py`), identity, profiles and settings (`identity.py`, `user_context.py`, `demo_profiles.py`), the one-record SQLite store (`store.py`) | yes |
| `guidance/` | V3.1 guidance: 96-configuration catalogue, 525-feature encoder, content models, 3.1 feasibility and composition (`content_v31.py`, `v31_pipeline.py`), frontend API (`frontend_*.py`), journey store, Inspector summary, demo-accepted wording (`provisional.py`), the 3.0 flavour that V3.1 builds on | yes |
| `learning/` | Shared Gaussian LinTS: numerical posterior (`posterior.py`) and the policy model and store (`lints.py`) | yes |
| `procedures/` | Plan input, canonical procedure graph, measurements, verified overlays (`canonical.py`), official and demo procedures, registration | yes |
| `preparation/` | LLM-assisted content preparation: provider (`llm_provider.py`), V1 wording generation and prepared wording, V2 overlay drafts, the preparation job queue (`jobs.py`), 3.x content drafting and service, review and wording CLIs | yes (queue, content service, captured-label reader); generation only when enabled |
| `compat/` | Kept for existing contracts: V2 journeys and policy (`/v2/*`, `/workspace/sessions/{id}/guidance`), V2 catalogue and encoder (their manifest is checked when the workspace database opens), V2 document finalisation | yes, mounted to preserve the API |
| `studies/` | Offline synthetic training, evaluation and replay (3.1 study, 3.0 study, V2 simulation and transfer, fixture builders) | no |
| `legacy/` | V1 modules used only by `dev_main` and its operator tools (V1 policy, V1 stores, adjustments, corrections, pipeline traces, migrations, prior tools) | no |
| `models/` | Shared Pydantic data models | yes |
| `main.py`, `api/routes.py`, `core/adapter.py` | Team Docker app and C2 contract stub | separate app |
| `errors.py` | `StateStoreError`, shared by host, preparation and legacy stores | yes |

Rule: `guidance`, `learning`, `procedures`, `host`, `compat` and `preparation` never import `studies` or `legacy`.
`guidance` and `learning` never import `compat`; it is reached only from `host` (the `/v2/*` routes, the
`WorkspaceRuntime` assembly, the preparation-status route) and from `procedures/registration.py` (V2 document finalisation).

## Request flow (V3.1)
`/workspace/guidance/*` → `guidance/frontend_api.py` → `guidance/frontend_runtime.GuidanceAPI`:
context (identity settings + 3.1 settings table) → `content_v31.evaluate31` (feasibility) → `guidance/features.encode`
(525) → `learning/lints.PolicyStore.select` (shared Gaussian LinTS, `learning/posterior.py`) → `v31_pipeline.compose31`
+ `frontend_presentation` → `journey_store` (`journeys.sqlite3`). Eligible ratings update `policy.sqlite3` once.

## Storage (unchanged)
- `state.sqlite3`: table `c4_workspace_state`, one JSON record (V2 manifest, rng, V2 journeys, identity, registrations).
- `journeys.sqlite3`: V3.1 journeys, events, ratings and 3.1 settings.
- `policy.sqlite3` + checkpoint `.npz`: posterior state, manifest and accepted updates.

## Old → new module paths
| Old | New |
|---|---|
| `app.v2.api`, `app.v2.workspace_api`, `app.v2.identity` | `app.host.application`, `app.host.routes`, `app.host.identity` |
| `app.core.user_context`, `app.core.demo_profiles` | `app.host.user_context`, `app.host.demo_profiles` |
| `app.v2.runtime`, `app.v2.catalogue`, `app.v2.features` | `app.compat.v2_runtime`, `app.compat.v2_catalogue`, `app.compat.v2_features` |
| `app.core.procedure_input/procedure_graph/procedure_features/scaffolds/official_procedures/demo_procedures` | `app.procedures.<same name>` |
| `app.v2.content`, `app.v2.measurements`, `app.v2.registration` | `app.procedures.canonical`, `app.procedures.measurements`, `app.procedures.registration` |
| `app.guidance.policy` | `app.learning.lints` (kernel: `app.learning.posterior`) |
| `app.core.llm_provider/explanations/explanation_store/prepared_wording/wording_service/wording_views/presentation` | `app.preparation.<same name>` |
| `app.v2.preparation`, `app.v2.preparation_jobs` | `app.preparation.overlay_drafts`, `app.preparation.jobs` |
| `app.guidance.service`, `app.guidance.preparation`, `app.guidance.editor` | `app.preparation.content_service`, `app.preparation.content_drafts`, `app.preparation.review_cli` |
| `app.wording_artifacts`, `app.content_artifacts` | `app.preparation.wording_cli`, `app.preparation.content_cli` |
| `app.guidance.{synthetic31,procedures31,experiment31,replay,plots,synthetic,experiment,decision}` | `app.studies.<same name>` |
| `app.v2.{simulation,transfer,workspace_experiment,fixture,export_fixture}` | `app.studies.v2_<same name>` |
| `app.api.{adjustments,guidance,demo_profiles,pipeline_trace}` | `app.legacy.api_<same name>` |
| `app.core.{adjustments,adjustment_store,corrections,guidance_access,pipeline_trace,standard_guidance,state_store,postgres_state_store,prior,navigation_migration}`, `app.policy_runs` | `app.legacy.<same name>` |
| `app.core.policy` | `app.legacy.v1_policy` |

## Remaining dependencies (intentional)
- The live app mounts `compat/` because `/v2/*` and `/workspace/sessions/{id}/guidance` are kept, the frontend's V2
  inspector hash reads `/v2/journeys/{id}/inspector`, research scripts read `/v2/policy`, and the workspace database
  record contains the V2 manifest, rng and journeys.
- Saved identity settings are validated with the V2 `Context` (`compat/v2_catalogue.py`), and identity revokes learning
  on V2 journeys when personalization or constraints change; changing either would change behaviour.
- Registry entries still carry the V2 canonical document, finalised with captured V1 prepared labels
  (`compat/v2_documents.py` → `preparation/wording_views.py`); it is served by `/v2/*` and `/dev/v1/procedures` and its
  preparation status drives the startup queue.
- `studies/synthetic.py` and `studies/synthetic31.py` fingerprint their own source bytes: editing them changes the
  simulator fingerprints recorded in the study reports.
- `compat/v2_catalogue.Configuration` and `host/application.Rating` pin `__module__` so the published OpenAPI component
  names stay unchanged.

## Validation
`python -m pytest tests -q` (includes `tests/test_architecture_golden.py`). `python -m tests.architecture_golden` compares
against the pre-refactor baseline without pytest. Never regenerate the fixture (`--write`) to make a refactor pass.
