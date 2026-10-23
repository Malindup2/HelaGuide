# C4 dependency and cleanup audit

Method: import graphs were computed from the real entry points (frontend from `src/main.tsx`, resolved case-insensitively and including dynamic `import()`; backend from `app.workspace` and `app.v2.api`, including imports inside functions). They were then cross-checked against tests, research scripts, `service/Dockerfile`, `docker-compose.c4.yml`, CLI commands in the READMEs, and the LLM content-preparation pipeline. Backup of the state before cleanup: branch `c4/final-v31-backup` (`154b0c7`).

## Outcome (2026-10-23)
Only earlier V1/V2 citizen-interface code that nothing imports from `main.tsx` was removed, together with the tests that covered nothing else. **No backend module was removed.**

Evidence the change is safe:
- The production bundle built from `c4/final-v31-backup` and the bundle built after cleanup are **byte-identical** (`index-CZOl5PZW.js`, `index-DnHaVs5n.css`). The UI is unchanged.
- Backend: 647 passed, 24 skipped, both before and after (backend untouched).
- Frontend: `tsc -b`, `eslint .` and `vite build` pass. `vitest`: 18 files / 161 tests pass. Before cleanup it was 31 files / 325 tests; the difference is exactly the 13 removed legacy test files.
- Policy checkpoint SHA-256 `71a7768f…ace43` unchanged. No `.env`, database, checkpoint or research evidence touched.

### Removed (`demo-frontend/src`)
| Files | What it was | Evidence |
|---|---|---|
| `adjustments/*` (incl. `adjustments.css`) | V1 presentation-adjustment panel | not reachable; css only imported by the removed panel |
| `feedback/{FeedbackPanel,api,contracts,flow,types}` | V1 feedback panel | not reachable; `feedback.css` kept (imported by `main.tsx`) |
| `guidance/{GuidanceWorkspace,RelationshipMap,api,contracts,episode,rendering,scaffoldModel,types,wording}` | V1 guidance workspace | not reachable; `scaffolds.css` kept (imported by `main.tsx`) |
| `guidance-v2/{ProcessMap,WorkspaceGuidance,semantics}`, `guidance-v2/card/*` except `parts.tsx`, `guidance-v2/compare/*` | V2 guidance card, comparison sheet and map | not reachable; `card/parts.tsx` kept (icons re-exported by `citizen/ui.tsx`) |
| `inspector/*` | V1 pipeline inspector UI | not reachable. The live `#c4-v2-inspector` / `#pipeline-inspector` hashes render `V2App`, which does not import it |
| `profiles/{ContextSummary,ProfileSettings}` | old profile settings | replaced by `citizen/ProfileContext.tsx` |
| Tests: `tests/{action-requirements,adjustments,feedback,guidance,pipeline-inspector,scaffolds,source-layout,wording-ui}`, `tests/fixtures/*`, `guidance-v2/{card,corrections,interaction,v2}.test.tsx`, `guidance-v2/compare/compare.test.ts` | tests of the removed code only | — |
| `guidance-v2/unified.test.tsx` (edited) | kept the `VersionRoute` routing test; removed the cases that rendered the removed V2 card | — |

### Retained on purpose (category, reason)
| Module(s) | Reason |
|---|---|
| `app.main`, `api/*`, `core/adapter.py`, the adjustments/corrections/pipeline_trace/guidance_access/standard_guidance/postgres store modules | `service/Dockerfile` starts `app.main:app` (team docker-compose, port 8004, C2 `Plan` render stub); `dev_main` and its tests use them |
| `core/llm_provider`, `explanations`, `wording_service`, `wording_views`, `prepared_wording`, `explanation_store`, `presentation`, `v2/preparation*`, `guidance/{service,preparation,sources,editor,registry,content,content_v31,provisional}`, `wording_artifacts.py`, `content_artifacts.py`, `dev_main.py`, `openai` | LLM-assisted content preparation: provider and prompts, generation, grounding validation, operator CLIs and their tests |
| `guidance/{synthetic,experiment,decision,replay,plots}` | reproduce the 3.0 evidence `PP1-SYNTHETIC-RESULTS.json` |
| `guidance/{synthetic31,procedures31,experiment31}` | the 3.1 study |
| `v2/simulation.py`, `transfer.py`, `workspace_experiment.py` | V2 experiment cited in research docs; documented reproduction CLIs; tested |
| `policy_runs.py`, `core/navigation_migration.py`, `models/runtime_state_v1*.py` | expert-prior and state-migration CLI (`service/POLICY-PRIORS.md`); tested |
| `v2/fixture.py`, `v2/export_fixture.py`, `guidance-v2/fixture.json` | generate `research/data/v2/practice` (a registered procedure) and the fixture used by `presentation.test.ts` |
| `v2/*` core, `guidance-v2/{VersionRoute,V2App,parts,presentation,types,workspaceClient,v2.css}` | live host and routing despite the version names |

## Remaining improvements (not done; each changes live code and needs separate approval)
1. Extract `_GaussianPosterior` from `core/policy.py` (the V2 policy file) into its own module.
2. Decouple `v2/registration.finalize` from the legacy wording pipeline.
3. Rename the live `v2/*` and `guidance-v2/*` modules; move `VersionRoute` and the icons in `card/parts.tsx` into `citizen/`.
4. Remove the unreferenced stylesheets `App.css`, `index.css`, `shell/shell.css`, and unused rules in `styles.css`.
5. Retire the legacy `/v2/*` and `/dev/v1/*` routes and the V2 inspector hash once no demo or test needs them; then the V1 backend modules used only by `dev_main` can follow.
6. Move the team Docker entry from `app.main:app` to the V3.1 app, which would free the C2 stub modules.
