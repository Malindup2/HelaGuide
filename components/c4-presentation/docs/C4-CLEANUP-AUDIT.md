# C4 dependency and cleanup audit

Method: import graphs were computed from the real entry points (frontend from `src/main.tsx`, resolved case-insensitively and including dynamic `import()`; backend from `app.workspace` and `app.host.application`, including imports inside functions). They were then cross-checked against tests, research scripts, `service/Dockerfile`, `docker-compose.c4.yml`, CLI commands in the READMEs, and the LLM content-preparation pipeline. Backup of the state before cleanup: branch `c4/final-v31-backup` (`154b0c7`).

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

## Backend consolidation (2026-10-24)
The backend was reorganised into one readable V3.1 structure without changing behaviour. The full layout,
old-to-new module map and remaining dependencies are in `service/ARCHITECTURE.md`.

Stages, each validated before the next:
0. Golden baseline `service/tests/architecture_golden.py` (+ fixture) captured from the unchanged backend: registry and
   document fingerprints, 3.1 feasibility and composed documents, 525-feature vectors, bit-exact LinTS scores and updates
   (fresh and from a copy of the trained checkpoint), the V1/V2 kernel users, OpenAPI of all apps, the stored workspace
   record, and an end-to-end HTTP flow with feedback on isolated stores.
1. Gaussian posterior extracted to `app/learning/posterior.py` (verbatim); the V1 policy keeps a subclass for its prior.
2. `action_navigation_order` moved next to `dependency_index` in `procedures/procedure_graph.py`.
3. `StateStoreError` moved to `app/errors.py`, so identity and wording no longer import the V1 store and V1 policy.
4. 61 modules moved into `host/`, `procedures/`, `learning/`, `preparation/`, `studies/`, `legacy/`, `compat/`; all
   imports, tests, research scripts and documented commands updated. The simulators that fingerprint their own source
   were moved byte-for-byte. Two schema classes keep their published OpenAPI component names (`__module__` pin).
5. V2 document finalisation moved to `compat/v2_documents.py`; registration keeps canonical registration only.
6. Record persistence extracted to `host/store.py`; identity is `WorkspaceIdentity`; V2 journeys and V2 guidance are
   `compat/v2_runtime.py` and `compat/v2_workspace.py`; `WorkspaceRuntime` is their explicit assembly.

Result: golden baseline identical after every stage; backend suite 653 passed / 24 skipped after every stage (647 + 6
golden); OpenAPI byte-identical to `c4/final-v31-backup`; checkpoint SHA-256 and simulator/encoder fingerprints unchanged.
No module was deleted (each historical one is still used by the V1 server, the V2 contracts, research reproduction or
the live database format); they are now separated by package instead of mixed into the live code.
