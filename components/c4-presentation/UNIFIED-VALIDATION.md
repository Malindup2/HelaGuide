# Integrated C4 verification — 2026-10-21

## Verified release state

- Branch: `c4/scaffolding-dimensions`.
- Committed V2 starting checkpoint and unchanged HEAD: `449451e`.
- Original V1 branch remains at `e9b7e9cf7e604c4574dd4ed3afa11f8acbeec68e`.
- No commits, pushes, merges, branch switches or history rewrites performed.
- Tracked and untracked repository changes audited: all inside `components/c4-presentation/`.
- `git diff --check` passed. `service/app/compat/v2_features.py` has no diff: ordering, scaling and 515-feature meanings remain unchanged.
- Active application: `app.workspace:app` on 8018; original citizen workspace on 5173; historical `#c4-v2` is an alias, not another citizen application.

## Executed automated checks

| Check | Actual result |
|---|---|
| Complete backend regression | **364 passed, 24 skipped**, one dependency deprecation warning |
| Frontend regression | **142 passed**, 12 files |
| TypeScript project build/check | Passed |
| Vite production build | Passed; 34 modules |
| ESLint | Passed, exit 0 |
| Original/manual support-fit attribution | Passed, including duplicate receipts and consent/hard-requirement revocation |
| 96 configurations and 515-vector mathematics | Existing tests passed, including joint Thompson argmax, normalization, 416/506 ablations and exact feature calculation |
| Profile/service familiarity and saved preference inputs | Passed; one profile uses distinct NIC/birth familiarity; actual score features verified |
| Accessibility and explicit locks | Passed; candidate exclusions, stale context, retired incompatible views, no lock weakening |
| Registration and canonical relationships | Passed; source/evidence validation, conditional joins, registered-input recovery, XOR versus joint requirements |
| Content preparation/publication | Passed using offline fixtures/fake provider; pending content rejected, digest/source checks, graph relationships immutable during publication, frozen old views, restart recovery |
| Explicit source-copy safety | Passed; source read-only hash stable, no 656-coefficient import, no cross-mode profile evidence import, legacy semantic review |
| Saved-model recovery | Passed for interactive and trained states |
| Repeated synthetic run | Same schedules, evaluation trials and posterior fingerprints for 416/506/515 |

The 24 skipped tests require an external PostgreSQL test DSN. That DSN was not configured. The warning is Starlette's existing httpx TestClient deprecation; no application test failed.

Backend command, from C4:

```powershell
service/.venv/Scripts/python.exe -m pytest service/tests --basetemp=service/.local/v2/unified-final-semantic-regression -q
```

Frontend commands, from `demo-frontend/`:

```powershell
$env:VITE_C4_API_BASE_URL = "http://127.0.0.1:8018"
node node_modules/typescript/bin/tsc -b
node node_modules/vitest/vitest.mjs run
node node_modules/vite/bin/vite.js build
node node_modules/eslint/bin/eslint.js .
```

Use an unused C4-owned `--basetemp` directory when retaining earlier test artifacts. No full repository test suite or root configuration was changed.

## Actual browser verification

| Scenario | Observed result |
|---|---|
| V1 workspace and onboarding | Professional shell, guest/profile choices, procedure catalogue and saved-profile creation work |
| Profile restoration | Saved context restored after reload and backend restart |
| One profile, different procedures | NIC uses its reported familiarity; practice remains unknown until reported; confidence reused without another questionnaire |
| Saved preferences | Editing navigation/explanation settings succeeds; the learned selection can still choose another navigation state |
| Accessibility | Disallowing diagrams disables Show Map; changing hard requirements retires the old view and asks for fresh guidance |
| Actual original feedback | Visible original adaptive view accepted a rating; revision/count/fingerprint changed |
| Manual feedback | Hiding a map/adding recap created child views; adjusted rating reported no policy update |
| Guest standard guidance | Overview/source guidance works; guest rating reports no policy update |
| Earlier-step recap | Appears beside a later action; uses actual earlier displays, preserves conditional summaries, explicitly says completion is not confirmed |
| Sources and requirements | Natural titles, required source text, conditional routes, charge qualifications, no calculated total |
| Process map | Desktop supplied relationships/agency labels, enlarge/hide, text equivalent; 390px layout uses readable integrated text cards |
| Research Inspector | Actual original context/sources, feasible scores, 515 named features, frozen content and current posterior; GET reads do not train |

Screenshots are actual browser captures, retained locally and ignored by Git:

- `output/unified/workspace-desktop.png`
- `output/unified/adjusted-guidance-desktop.png`
- `output/unified/guidance-mobile.png`

The mobile check used the existing preview iframe at 390 CSS pixels. It is not a physical-device, touch or screen-reader certification. The old standalone citizen form has been retired; the preview renders the same main application.

## Research experiment and prepared demonstration state

Two independent executions used seed17, 40 training trials and 12 held-out evaluation trials per encoder. Both ran through saved profiles, the effective-context resolver, actual selection, visible exposure, explicit feedback and kernel updates. Training probabilities were not given to the selector.

| Model/baseline | Expected synthetic reward |
|---|---:|
| 416 pairwise | 0.391189 |
| 506 three-way | 0.355129 |
| 515 complete | 0.382635 |
| Minimal feasible baseline | **0.663810** |
| Rich feasible baseline | 0.217240 |
| Uniform feasible baseline | 0.387720 |

All reload checks passed. Schedule hashes, per-trial evaluation results and posterior fingerprints matched across repeat runs. Output directories are `service/.local/v2/workspace/experiments/20261021-seed17` and `20261021-seed17-repeat`.

The minimal baseline outperformed the learned encoders. These outcomes are synthetic, small-sample and do not establish human benefit or superiority of the 515 representation. Preferences were wired into features but preference-specific learning benefits were not established by this experiment. One-hot held-out familiarity/confidence categories have no guaranteed interpolation.

A separate trained copy is prepared and reopened successfully at `service/.local/v2/workspace/simulation/trained-pp1-seed17.sqlite3`: seed17, 515 features, 40 accepted simulated updates. The interactive seed0 store remains separate with one test update. See UNIFIED-README.md for switching the runtime configuration without changing the frontend.

## Preservation and outstanding limits

- Original V2 state was read through a read-only SQLite connection: one update and fingerprint `69259357b44cf7252f824a62eb34dcbc29ee35c56bf32b5fd32cb182834681a2`, matching the earlier checkpoint record.
- No original V1 PostgreSQL database or 656-dimensional posterior was opened for writing, migrated or reset. Its branch reference is unchanged, and V1 regression tests pass. A live restart against that original PostgreSQL installation was not performed; the external PostgreSQL integration tests were skipped.
- Integrated data uses a different table and workspace path; incompatible V1/V2 snapshot writers cannot share it. No real participant data was imported.
- Some official procedures still need human-reviewed full V2 explanation variants. Safe source instructions and prepared demo labels remain usable; unsupported expansion states are filtered and offline preparation jobs are queued.
- No live LLM request was executed. Generation has an explicit confirmation flag and bounded packet limits; human review remains necessary before publication. Large generation packets may require manual preparation or bounded batches.
- Full gateway/team C2 deployment, authenticated participant accounts/consent, real-user evaluation and physical assistive-technology testing remain external work. Shared Plan v1 and other team components were not modified.
- PP2 history-transfer scoring is intentionally absent; procedure-scoped evidence is retained.
- Snapshot persistence is designed for a single local research process, not a production-scale distributed service.
