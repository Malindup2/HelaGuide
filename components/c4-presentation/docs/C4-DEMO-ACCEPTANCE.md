# Local research demo acceptance of cached official-procedure wording

Branch `c4/final-guidance-ux`. D3 is unchanged (v3.1: the primary Concise/Detailed text always shows; D3 hides only the separate supplement). No v3.2, no retraining, no change to the policy, encoder, posterior, checkpoint or recorded synthetic evidence.

## What the mode is
- `C4_DEMO_ACCEPTED_CONTENT=true` (local demo only; off by default) makes ordinary guidance for Birth Certificate Copy, NIC Amendment and Private Company use the cached AI-assisted wording in `research/data/guidance/provisional-v31/` (built from the existing prepared demo drafts and the official-source passages; no regeneration).
- Provenance is preserved: every file stays `draft`, origin `demo_mock`, no review record. The API reports `content_state: demo_accepted`, `review_kind: project_owner_demo_acceptance_automatic_checks` and `independent_government_validation: false`. The card says: "Local research demo wording. AI-assisted and checked only by automatic source-grounding checks. The project owner accepted it for this demonstration; no expert or government body has reviewed it." Nothing claims expert, government or independent approval.
- Validation is not bypassed. Claim coverage, fact ownership, number/name grounding and contradiction checks gate every file (`provisional.check`). I tightened nine Detailed/supplement sentences (listed as `OVERRIDES` in `research/build_provisional_content.py`) where Detailed was barely richer than Concise or repeated a fact already on a card; each is derived from the source passages or the verified graph and passes the same checks.
- Standard (guest) guidance, LinTS-selected journeys, research previews and manual adjustments all use the accepted wording when the mode is on. Without the mode the strict reviewed-only behaviour is unchanged (tested).

## Feasible configurations (of 96 nominal)
| Procedure | Before (reviewed only) | After (demo accepted) | Still unavailable and why |
|---|---|---|---|
| Birth certificate copy | 4 | 32 | Map: parallel coverage unknown. Phases: one stage, no verified grouping |
| NIC amendment | 4 | 32 | Map: parallel coverage unknown. Phases: one stage |
| Private company | 4 | 64 | Map: parallel coverage unknown (four preparation steps feed one check; no order or independence asserted) |

Concise, Detailed, Disclosure ON/OFF, Overview/Guided, inline connections and recap are feasible for all three; phases are feasible for the company procedure only. The earlier 48-for-NIC figure included the map, which stays an explicit labelled research preview (`allow_provisional`, relaxed map rule). In ordinary journeys the map is refused, because showing edges without verified parallel coverage could imply false parallelism. This is a structural limit, not a wording-approval limit.

## Compatibility with the trained policy
- The 525-feature encoder reads measurements of the verified graph, the citizen context and the configuration. It never reads wording, and `policy.manifest()` contains only the content schema string, so the checkpoint manifest check, encoder and posterior accept the expanded feasible set unchanged (live check: 32 candidates scored, 525 features, manifest fingerprint unchanged, checkpoint file hash identical before and after).
- Not claimed: the 5,000-observation synthetic study used the four fictional procedures only. The official procedures' graph measurements and these 32/64 configurations were never evaluated, so the policy's choices for them are genuine posterior-sampling decisions but out-of-distribution; they are not validated. The historical results are untouched, and no new evaluation was run (no outcome data exists for these procedures, and an author-defined simulator would not be evidence).
- The decision record gains `content_state: demo_accepted`, so these decisions are distinguishable from the study's.
- Live tests ran against a copy: the app starts a fresh policy folder and restores the checkpoint into it; the original file hash is unchanged.

## Evidence (all from the running trained app, `docs/C4-DEMO-ACCEPTED-LIVE.json`, 20 draws per cell)
- Experienced (familiarity 5, confidence 5) citizens received overview + inline connections with Concise in 80% (NIC) to 95% (company) of draws; the remaining draws were Detailed with Disclosure ON. Novices (familiarity 1, confidence 1) received Detailed + Disclosure ON in every draw, and guided navigation in 20/20 (NIC), 19/20 (birth) and 14/20 (company) draws, with Earlier steps ON in most guided NIC/birth draws. Selections differ by citizen; richer support is not forced, and the policy is stochastic (these are frequencies, not guarantees).
- Feedback: first rating moved the posterior 5000 to 5001; a replay returned the identical receipt without a second update; a second distinct rating on the same view was refused (409); a rating after a manual adjustment was refused (409); a manual-view rating and a guest rating did not change the posterior (guest refused with 403).

## Changed files
Backend: `service/app/guidance/frontend_runtime.py`, `frontend_contracts.py`, `frontend_api.py`, `app/workspace.py` (mode and labels). Content: `research/build_provisional_content.py` and `research/data/guidance/provisional-v31/*.json`. Tests: `service/tests/test_demo_accepted.py` (17). Scripts: `research/export_demo_accepted_examples.py`, `research/verify_demo_accepted_live.py`. Frontend: `GuidanceCard.tsx` (local-demo note), `Routes.tsx` (route fee also shown in the guided route choice), `citizen.css` (narrow qualification note), `types.ts`, `__tests__/demo-accepted.test.tsx`, `examples.ts`. Evidence: `docs/examples/frontend-api-3.1-demo-accepted-2026-10-22/`, `docs/screenshots-demo-accepted/`.
