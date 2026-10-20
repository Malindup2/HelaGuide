# C4 V2 verification record

Date: 2026-10-20. Branch: c4/scaffolding-dimensions. All results are local research verification, not real-user validation.

## Tests

- Full backend regression: 347 passed, 24 skipped, one Starlette/httpx deprecation warning (100.57 s). This run preceded the final two added V2 tests and measurement-label/control-availability changes.
- Final targeted V2 backend suite: 12 passed (6.72 s), including the two additions. These overlap the full-suite tests; do not add the counts.
- Final frontend: 135 passed across 11 files; production build passed. ESLint passed (exit 0).
- Skips: all 24 require C4_TEST_POSTGRES_DSN. V1 PostgreSQL integration was not exercised against an external database. No V1 database was reset or used for V2.

## Live browser and recovery

- Actual policy selection rendered guided, expanded explanation, collapsed optional information, process map, recap on and summary off in the desktop browser.
- Rating was disabled until an action entered the viewport. Original-view about-right feedback advanced the policy from revision 0 to 1.
- Manual map hiding, independent disclosure/depth changes, summary and earlier-step recap were exercised. Adjusted-view feedback reported no policy update.
- Backend restart preserved revision 1, accepted-feedback count 1 and fingerprint 69259357b44cf7252f824a62eb34dcbc29ee35c56bf32b5fd32cb182834681a2.
- Inspector displayed actual selection, candidate scores and model state. Its read-only behavior is also covered by API tests.
- 390px iframe preview checked responsive CSS and the compact full-process equivalent. Physical mobile devices, touch and screen-reader applications were not tested.

## Synthetic experiment

Output: service/.local/v2/experiments/resume-20261020-seed17 (ignored local artifacts). Seed 17; 120 actual update trials per encoder and 60 held-out evaluations per encoder; all reload checks passed. Separate two-run seed-91 regression confirms reproducibility of decisions/outcomes and posterior fingerprints. UUIDs and timestamps are intentionally not identical.

| Encoder | Expected synthetic reward | Synthetic oracle regret |
|---|---:|---:|
| pairwise | 0.432275 | 0.292506 |
| threeway | 0.410732 | 0.314050 |
| full | 0.412834 | 0.311948 |

Common baselines: minimal 0.665526; rich 0.188490; uniform 0.372137. The minimal baseline beat every learned encoder in this run, and pairwise beat full. This does not support a claim of superior V2 learning quality. It verifies the implemented selection/update/evaluation pipeline and exposes the need for multi-seed, broader-generator and participant evaluation. Do not tune the generator merely to make the demonstration win.

## Remaining boundaries

- Shared chat/gateway/C2 deployment integration remains external; C4 owns the local adapter and reusable renderer.
- Official examples remain bounded snapshots. Reviewed expanded variants are available for the fictional practice fixture; new official variants require source review.
- LLM provider integration was tested offline through its interface; no paid/live provider call was made.
- V2 uses isolated SQLite snapshots, not a V2 PostgreSQL deployment. Snapshot writes grow with trace history; this is bounded research infrastructure, not a production-scale event store.
- Capabilities are local access tokens, not full participant authentication/consent. No automatic reward is inferred from activity. PP2 individual history adjustment remains explicitly unimplemented as required.
- No automatic commits, pushes or branch changes were performed.
