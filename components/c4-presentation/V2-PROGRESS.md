# C4 V2 implementation checkpoint

Branch: c4/scaffolding-dimensions. Baseline: e9b7e9c. Scope: C4 only.
Updated: 2026-10-20. Approved local V2 implementation implemented and verified; final boundary audit and lint passed. See V2-VALIDATION.md for research and deployment limitations.

## Implemented
- Separate app.v2 API/runtime, 96-configuration catalogue, hard capability/lock filtering.
- 515 named normalized features, 416/506 ablations, existing Shared LinTS numerical kernel.
- Isolated SQLite V2 state, atomic updates, RNG recovery, original/manual view attribution.
- Graph-bound C4 overlay, conditional joins, ownership, fictional practice fixture; six existing examples retained.
- Conversational React route, all six supports, process map, journey recap, compact feedback, Inspector.
- Synthetic selection/exposure/feedback training and held-out evaluation runner.
- Offline content preparation/review, graph-bound approved-artifact registry and integrity tests.
- Route-aware guided browsing, real control-visibility opportunities, feasibility-aware controls, scoped fees, desktop/mobile process maps.
- V2-README.md contains exact backend/frontend/training commands and the 2.5-minute PP1 script.

## Verification
- Full backend regression: 347 passed / 24 skipped (external PostgreSQL test DSN absent); one dependency deprecation warning.
- Final targeted V2 backend suite: 12 passed, including offline-provider, opportunity, persistence, concurrent-write and reproducibility tests.
- Final frontend suite: 135 passed / 11 files. Production build passed. Final lint passed (exit 0).
- Browser: actual selection, action exposure, original-view reward update, manual adjustment exclusion, recap and responsive 390px layout checked.
- Backend restarted with revision/count/fingerprint unchanged. V2 simulation feedback count remains 1 in the interactive store.
- Seed17 experiment: 120 train / 60 held-out trials per encoder (416, 506, 515); all reload checks passed. Minimal baseline outperformed learned encoders. See V2-VALIDATION.md for exact results; no claim of human benefit or superior 515-feature performance.

## Remaining external or unverified work
- Shared HelaGuide chat/C2 deployment integration, participant authentication/consent and real-user evaluation.
- Live LLM call, physical mobile/screen-reader testing, and optional PostgreSQL integration tests were not executed.
- Official expanded wording requires reviewed source artifacts; do not invent it or relax feasibility.
- PP2 history-transfer scoring intentionally not implemented.
- Local research functionality is in place; snapshot storage has scaling limits documented in V2-README.md.

## Final boundary audit
1 tracked modification (C4 frontend route mount), 0 staged files, 28 untracked implementation/documentation files: all inside C4. Git diff --check passed. Branch remains c4/scaffolding-dimensions; HEAD remains e9b7e9c.

## Safety and resume
No Git history changed. Only existing tracked modification is C4 frontend main.tsx mounting the V2 route; V1 remains default. No V1 database/state migrations or resets. V2 data stays in service/.local/v2. Verify branch/status and this checkpoint before resuming. Preserve all existing work. All writes must remain within components/c4-presentation/.
