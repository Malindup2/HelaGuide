# C4 dependency and cleanup audit

Method: import graphs were computed from the real entry points (frontend from `src/main.tsx`; backend from `app.workspace`), then cross-checked against tests, `Dockerfile`, `docker-compose.c4.yml` and the READMEs. **Nothing has been deleted.** Every removal below is a proposal that needs your approval, and all of it is recoverable from Git history.

Classes: **A** active and required, **B** historical research evidence or reproducibility dependency, **C** safe to remove once approved (no active dependency; only its own legacy tests), **D** uncertain, needs manual review.

## Frontend (`demo-frontend/src`): 38 files reachable from `main.tsx`, 43 non-test files not reachable
| Area | Files | Class | Evidence and remaining dependency |
|---|---|---|---|
| `citizen/` | the active interface (Workspace, GuidanceCard, Research, api, model, tests) | A | rendered by `App.tsx`; the only citizen workflow |
| `api/`, `app/useWorkspace.ts`, `app/research.ts`, `profiles/ProfileOnboarding.tsx`, `profiles/profileDraft.ts`, `session/*` | identity workflow reused by `citizen/Workspace` | A | imported by the active app |
| `guidance-v2/VersionRoute.tsx`, `V2App.tsx`, `workspaceClient.ts`, `presentation.ts`, `types.ts`, `v2.css` | hash routing and the old inspector routes | D | `VersionRoute` is the app root and still serves the legacy `#inspector` routes through `V2App` |
| `guidance-v2/card/parts.tsx` | icons | A (relocate) | `citizen/ui.tsx` re-exports its icons; move them into `citizen/ui.tsx` before any removal of `guidance-v2/` |
| `guidance-v2/card/*`, `compare/*`, `ProcessMap.tsx`, `WorkspaceGuidance.tsx`, `semantics.ts` and their 7 tests | previous Guidance Card, comparison and map | C after relocating `parts.tsx` | not reachable; only `guidance-v2/*.test.tsx` import them. Coverage is superseded by `citizen/__tests__` (card, card31, model, journey, workspace) |
| `guidance/*` (V1 GuidanceWorkspace, rendering, scaffoldModel, wording, episode, RelationshipMap) | V1 citizen guidance | C | not reachable; used by `tests/guidance.test.tsx`, `scaffolds.test.tsx`, `wording-ui.test.tsx`, `source-layout.test.tsx` only. `guidance/scaffolds.css` is still imported by `main.tsx` and must be kept or relocated first |
| `adjustments/*`, `feedback/*` (except `feedback/feedback.css`, imported by `main.tsx`) | V1 adjustment and feedback panels | C | tests only |
| `inspector/*` | V1 pipeline inspector | D | reachable only through legacy `#inspector` routes of `V2App`; decide whether those routes are retired |
| `profiles/ContextSummary.tsx`, `ProfileSettings.tsx` | old profile settings | C | not reachable; replaced by `citizen/ProfileContext.tsx` |
| `App.css`, `index.css`, `shell/shell.css`, `styles.css` | old styles | D | `styles.css` is imported; the others are unreferenced |
| `tests/*` (10 legacy files), `tests/fixtures/guidance.ts` | legacy tests | B/C | they protect code that is only reachable from legacy tests; delete together with that code, not before |

## Backend (`service/app`): 64 of 108 modules reachable from `app.workspace`
| Area | Class | Evidence |
|---|---|---|
| `guidance/` (content, content_v31, feasibility, composition, v31_pipeline, flavours, features, policy, frontend_*, journey_store, registry, service, sources, preparation, demo, catalogue, api) | A | active runtime and 3.0 default |
| `guidance/synthetic.py`, `experiment.py`, `replay.py`, `plots.py`, `decision.py` | B | the preserved 3.0 study, its replay and the 3.0 selection-record contract; tests depend on them. Keep: they reproduce `PP1-SYNTHETIC-RESULTS.json` |
| `guidance/synthetic31.py`, `experiment31.py`, `procedures31.py` | A (research) | the 3.1 study |
| `guidance/editor.py` | D | local review tool; tested but not used by the app |
| `v2/` core (`api`, `identity`, `runtime`, `measurements`, `registration`, `catalogue`, `content`, `features`, `preparation*`, `workspace_api`) | A | active runtime foundations. Despite the V2 name this is the live host |
| `v2/simulation.py`, `transfer.py` | B | historical V2 reproduction |
| `v2/export_fixture.py`, `fixture.py`, `workspace_experiment.py` | D | no test or app import found; confirm they are not run by hand |
| `core/` guidance, scaffolds, policy, prior, procedure_*, wording_*, user_context, state_store, official_procedures, demo_* | A | imported by the active runtime |
| `core/adapter`, `adjustments`, `adjustment_store`, `corrections`, `guidance_access`, `navigation_migration`, `pipeline_trace`, `postgres_state_store`, `standard_guidance` and `api/*`, `models/adjustments`, `guidance`, `pipeline_trace`, `runtime_state_v1*` | A for `app.main` | `service/Dockerfile` and the root README start `app.main:app` on port 8004; the team's Docker setup depends on them. Not part of the citizen path, but not removable on this branch |
| `dev_main.py` | B | the V1 research backend (port 8016); README documents it |
| `content_artifacts.py`, `wording_artifacts.py`, `policy_runs.py` | D | CLI utilities; only `dev_main` and tests use them |

## Findings that block a safe bulk removal
1. `guidance/scaffolds.css`, `feedback/feedback.css` and `guidance-v2/card/parts.tsx` are still imported by active code.
2. `app.main:app` (the team's original service) and `app.dev_main:app` still depend on the V1 backend modules.
3. Legacy tests are the only coverage of legacy code. Removing code and its tests together is safe; removing tests alone is not.

## Proposed order (each step needs your approval)
1. Move the icon components from `guidance-v2/card/parts.tsx` into `citizen/ui.tsx`; move or inline the two imported stylesheets.
2. Remove `guidance-v2/card`, `compare`, `ProcessMap`, `WorkspaceGuidance`, `semantics` and their 7 tests; remove V1 `guidance/`, `adjustments/`, `feedback/` (keeping the css file) and their tests; remove `profiles/ContextSummary.tsx` and `ProfileSettings.tsx`. Evidence: unreachable from `main.tsx`; `citizen/__tests__` cover the replacing behaviour.
3. Decide whether the legacy `#inspector` routes and `inspector/` stay.
4. Leave the V1 backend and `app.main` in place until the team's Docker entry point is changed.
