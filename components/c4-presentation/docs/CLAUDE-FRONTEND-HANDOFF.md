# Claude frontend handoff: revised C4 Guidance API

Date: 2026-10-22. API `c4-guidance-api-1.0`; actions `c4-scaffolds-v3.0`; content `c4-guidance-content-3.0`. One existing `app.workspace` composition root. No new app/v3 application or frontend was created.

## Boundary and mandatory remaining PP1 work

The API is ready for source-grounded standard guidance and explicitly labelled research previews. **It is not a trained revised policy.** `POST /workspace/guidance/requests` with `mode=personalized` returns **503 revised_policy_unavailable**. No V2 coefficients, 515 features, sampled scores, probabilities or posterior updates are fabricated or reused for revised semantics.

A NEW Shared Gaussian LinTS encoder compatible with the six revised dimensions, including Segmentation, remains a **mandatory PP1 deliverable**. The proposed 525 terms require explicit approval, then fresh-posterior training from versioned synthetic context/configuration/reward observations and evaluation. The model must choose within the feasible set; no profile rules may substitute for it. Synthetic learning/evaluation are not performed in this phase. Procedure-specific historical score adjustment remains **PP2**, not a prerequisite for frontend integration or PP1.

The response envelope already reserves `selection.kind=shared_gaussian_lints`, executed scoring and a real `PolicyEvidence` manifest. These are schema definitions, not sample learned results. After the approved adapter is implemented, the same `/requests` mode and rendering contract can carry real selections. The frontend must use `status.personalized_selection_available`, `selection.kind`, `selection.policy`, and `controls`, not guess from profile labels. Current preview/manual/standard receipts always have null reward and no policy update. Future eligible feedback can use the receipt's validated reward/update fields without redesigning the card.

## Safe backend startup: a new isolated sandbox

Preserve an existing running server. In a new PowerShell terminal:

```powershell
Set-Location 'C:\Users\Lenovo\Desktop\HelaGuide\components\c4-presentation\service'
$c4FrontendRun = Get-Date -Format 'yyyyMMdd-HHmmss'
$env:C4_WORKSPACE_DATABASE = Join-Path (Get-Location) ".local\v2\workspace\frontend-$c4FrontendRun\state.sqlite3"
$env:C4_PREPARED_CONTENT_DIRECTORY = Join-Path (Get-Location) ".local\prepared-content\frontend-$c4FrontendRun"
if (Test-Path -LiteralPath $env:C4_WORKSPACE_DATABASE) { throw 'Choose a new sandbox path' }
$env:C4_WORKSPACE_MODE = 'simulation'
$env:C4_WORKSPACE_SEED = '0'
$env:C4_WORKSPACE_CONTENT_MODE = 'demo'
$env:C4_PREPARED_CONTENT_ENABLED = 'true'
$env:C4_PREPARED_CONTENT_MODE = 'demo'
$env:C4_PREPARATION_ON_MISS = 'false'
$env:C4_LLM_ENABLED = 'false'
$env:C4_DEV_LLM_ENABLED = 'false'
$env:C4_GUIDANCE_API_ENABLED = 'true'
$env:C4_RESEARCH_PREVIEWS_ENABLED = 'true'
.\.venv\Scripts\python.exe -m uvicorn app.workspace:app --host 127.0.0.1 --port 8019
```

Use another unused port if 8019 is occupied; do not kill unrelated existing processes. Open `http://127.0.0.1:8019/docs` and use the **Revised Guidance** tag. `GET /workspace/guidance/status` verifies the flags. Default API/research flags are false; disabled API routes return 404 and disabled research previews/inspection return 403.

The current frontend is unchanged. After implementing the frontend against this contract, use its existing API setting `VITE_C4_API_BASE_URL=http://127.0.0.1:8019`; keep the permitted development origin at 127.0.0.1:5173 or localhost:5173. Do not treat the current old renderer as the new API demonstration. Do not use VITE_C4_V2_API or old V2 response types for the new card. No frontend process was replaced during this phase.

The new content registry remains `<content-directory>/registry.sqlite3`; revised API settings/journeys/events are in `<content-directory>/frontend-api/journeys.sqlite3`. Its own manifest prevents opening an unrelated store. Preparation jobs reuse the existing worker under `<content-directory>/v2/jobs/`. The workspace identity host uses the explicitly selected sandbox database. Existing V1, standalone V2, integrated stores, coefficients and Git checkpoints were not migrated or reset.

## Exact endpoints

All endpoints below are on the same backend. Journey routes require `X-C4-Token`, matching the per-request `capability_token`. Generate a random token of 32-128 characters once per new request and reuse it on retries; it is never returned or persisted as plaintext by the revised journey store. Request/event IDs are stable UUIDs for retry safety.

| Endpoint | Purpose |
|---|---|
| GET `/workspace/guidance/status` | API schemas, mode availability, real visibility policy, mandatory remaining model work |
| POST `/workspace/guidance/guests` | Existing guest identity service; returns `session_id` and saved settings |
| GET / POST `/workspace/guidance/profiles` | Existing saved-profile service and V1 onboarding contract |
| PATCH `/workspace/guidance/profiles/{profile_id}/personalization` | Existing explicit consent/revision contract |
| GET `/workspace/guidance/procedures` | All seven registered procedures, titles, origin, limitations and completeness |
| GET `/workspace/guidance/context/{session_id}?procedure_id=...` | Effective service familiarity, confidence, revised preferences, restrictions, origins, composite revision |
| PATCH `/workspace/guidance/profile-context/{session_id}` | Saved service familiarity/confidence/accessibility through existing profile services |
| PATCH `/workspace/guidance/context/{session_id}` | Explicit revised six-dimension preferences/locks and stricter accessibility, with revision/idempotency |
| GET `/workspace/guidance/procedures/{id}/availability?session_id=...&language=en` | All 96 candidates, actual feasibility and reasons; **does not enqueue generation** |
| POST `/workspace/guidance/requests` | Complete standard guidance; personalized mode explicitly unavailable until new policy integration |
| POST `/workspace/guidance/research/previews` | Strict explicit configuration preview; unsupported combinations return 422 with reasons |
| GET `/workspace/guidance/journeys/{id}` | Frozen current view plus actual current interaction/recap state |
| POST `/workspace/guidance/journeys/{id}/events` | Attributed typed activity, never an inferred reward |
| POST `/workspace/guidance/journeys/{id}/views` | Validated manual child of a research preview, with parent view ID |
| POST `/workspace/guidance/journeys/{id}/ratings` | Research-preview fit diagnostics only; no reward or update; standard guests rejected |
| GET `/workspace/guidance/journeys/{id}/inspector` | Factual frozen request/feasibility/measurement/view evidence and real event records |

Do not consume `/v2/journeys`, old `/workspace/sessions/{id}/guidance` or `/workspace/content/guidance` as the revised citizen card. Those compatibility paths remain operational; the older content-verification endpoint can fall back on an unsupported preview, whereas this strict API rejects it.

## Request examples

In terminal 2, after backend startup:

```powershell
$c4ApiBase = 'http://127.0.0.1:8019/workspace/guidance'
$c4Guest = Invoke-RestMethod -Method Post -Uri "$c4ApiBase/guests"
$c4ApiToken = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$c4Body = @{
    request_id = [guid]::NewGuid().ToString()
    session_id = $c4Guest.session_id
    procedure_id = 'official-nic_amendment-v3'
    capability_token = $c4ApiToken
    mode = 'standard'
} | ConvertTo-Json -Depth 8
$c4Guidance = Invoke-RestMethod -Method Post -Uri "$c4ApiBase/requests" -ContentType 'application/json' -Body $c4Body
$c4Guidance.selection
$c4Guidance.document | ConvertTo-Json -Depth 25
```

A research preview uses the same session, a new request ID, `mode=research_preview` and a required full `configuration`, posted to `/research/previews`:

```json
{
  "navigation":"guided", "explanation":"detailed", "disclosure":"on",
  "relationships":"map", "recap":"on", "segmentation":"on"
}
```

This is genuinely feasible for `synthetic-practice-v2`, `synthetic-conditional-v1` and `synthetic-parallel-v1`. For `synthetic-linear-v1`, use `segmentation=off`. Each official snapshot currently has 4 unconstrained configurations: Overview/Guided x None/Inline with Concise, Disclosure OFF, Recap OFF and Segmentation OFF. Full Map is excluded because parallel coverage is unknown. Never convert a 422 into a silently altered configuration or generate an explanation locally.

`context` overrides are optional: familiarity/confidence 1-5 or explicit null, revised soft preferences and stricter constraints. Omitted values reuse saved settings; never ask the user again on every request. `expected_context_revision` optionally checks both identity and revised settings revisions. Conflicting saved locks, stale settings and changed hard restrictions are explicit 409 errors. Current soft preferences are recorded for the future encoder, not used to create rule-based selections. Standard is the fixed baseline, or the first baseline-compatible configuration required by hard constraints, labelled `constraint_standard`.

## Profiles and settings

Reuse onboarding's general questionnaire and existing identity IDs. Create requests have `profile_id=profile:<32 hex>`, display_name, personalization_enabled, and initial_context with service-specific familiarity reports, navigation_capability and accessibility. New native preferences/locks go through the revised context PATCH, not the V2 expanded/summary/collapsed fields. General settings edits use `ProfileContextPatch`: request_id, expected_identity_revision, familiarity list, optional confidence (null clears it), accessibility. The backend continues to perform service lookup and persistence.

`ContextPatch` has request_id, expected_revision `{identity,revised}`, optional replacement preferences/locks and optional restrictive accessibility `{no_guided,no_map,no_disclosure}`. Original saved accessibility restrictions cannot be relaxed by a request override. Existing changed-meaning preferences are shown as unimported data; they are not scorer inputs. Existing hard locks block new guidance until explicitly reviewed with the returned legacy lock fingerprint AND an explicit revised-lock replacement; no automatic inversion or reinterpretation occurs. A separate guest session remains available.

## Response contract and six mechanisms

Authoritative schema: `examples/frontend-api-2026-10-22/openapi.json` (15 paths, reachable DTO definitions). Python source: `service/app/guidance/frontend_contracts.py`. Every normal response uses:

- schema_version, journey_id, view_id, parent_view_id, session/procedure identity and title, creation time;
- `selection`: origin, exact applied configuration, action schema, label, scoring status, optional actual future policy manifest, learning eligibility;
- `preparation`: published/source_fallback state, job status, language/schema/fingerprints, origin and source-review scope;
- frozen effective_context, availability and document;
- current `interaction`, plus explicit `controls` booleans.

| Dimension | Fields and required frontend behavior |
|---|---|
| Navigation | `document.navigation`/`interaction.navigation`: active, previous/next, browsing IDs, source-derived layers and per-route entries. Guided may start with no active action until a route is selected. Browsing position is NOT execution/completion. Peer layers alone are NOT parallelism. |
| Explanation | `actions[].essential` always visible; `explanation_visible` supplies Concise or Detailed clarification selected by D2. The backend provides natural headings and source-grounded text; do not rewrite it from profile labels. |
| Disclosure | ON exposes `explanation_hidden` and `disclosure_available`. Only that remainder gets More/Less. OFF shows explanation normally. Essential instructions, conditions, fees, destinations and qualifications never enter a hidden remainder. |
| Relationships | Render `relationship_aid`, not every raw graph field. None has no extra aid; Inline has verified cues by action; Map has source edges, full logical join expressions, branches, parallel work, stage agencies and text equivalent. Never flatten `all_of`, `any_of` or `selected_option_of` into invented unconditional requirements. |
| Recap | Render ONLY `interaction.recap.items`. Action `recap` is intentionally null so unvisited prepared reminders cannot accidentally appear. Each item includes the actual qualifying event identity and `viewed_not_completed=true`. Empty means no recap panel. |
| Segmentation | `document.phases[]` has reviewed `label.text`, membership, purpose/basis and evidence. Group only when configuration ON. `phase_order=[]` means unordered groups: no invented phase progress/sequence. |

Routes remain mandatory in every configuration, even None/Concise/standard. `document.routes` contains exact conditions, selection logic and option action IDs. Changing focus is not eligibility or completion. In Guided, use server browsing IDs and active state after `route_focus`. A route switch does not modify the source or selection configuration.

`requirements.documents` and `requirements.fees` are scoped facts. Respect action/route/stage/service targets and condition IDs. Stage facts are not action payments. `source_context` carries verbatim passages about a fact, including qualifications and exclusions. `consult_source_context` does not license inventing a conditional/unconditional classification. Keep these facts/qualifications available outside disclosure; never sum charges (`total=null`) or repeat a stage fee as separate payments. Unknown destination/actor stays null; the essential source text remains available.

Source limits remain visible. Official snapshots use source_fallback and do not claim current government or independent validation. Fictional published content is internally **AI-assisted author-reviewed**, not human expert or government verified. Never relabel that provenance. Raw IDs/vectors/metadata belong in research inspection, not citizen action headings. Render source/prepared text as text.

## Events and earned recap

Always send current view_id and a stable event_id with X-C4-Token. Event names: view_displayed, step_visible, navigate, step_open, viewport_changed, explanation_open/close, route_focus, map_show/hide/expand/collapse, recap_open/close, overview_peek, source_open. Fields are validated per event type; unknown fields, actions, routes, sources and inactive view IDs are rejected. Duplicate matching IDs create no duplicate record; conflicting reuse returns 409.

- After actual essential display, send view_displayed with actual action_ids. This is exposure, NOT a visit.
- On explicit navigation/opening, send navigate/step_open with action_id; do not emit visits merely because the component mounts. These explicit events qualify recap.
- Overview also sends viewport_changed with currently visible action_ids, so recap does not repeat guidance still on screen. Until viewport evidence exists, Overview recap is suppressed.
- step_visible records measured visible_ratio, continuous dwell_ms and instrumentation_version. **Default visibility_policy is null** pending approved instrumentation parameters; raw measurements are recorded but do not qualify recap by themselves. The backend supports explicitly supplied versioned policy parameters (tested using test-only values). No product dwell threshold was silently chosen.
- Explanation opening is NOT evidence that the body was read and does NOT qualify a step visit by itself.
- route_focus uses branch_id and option_ids (XOR at most one; clearing restores route choice). Other-route reminders are excluded after switching. Same-layer parallel peers are not "earlier" recap.
- Map visibility/expansion and explanation disclosure are activity; changing a scaffold dimension uses POST views with parent_view_id and a full valid configuration. A child receives a new view identity; use it for subsequent events.

Receipts report server sequence/timestamp and, today, reward=null, policy_updated=false, learning_eligible=false. Records distinguish control availability from observed display. There is no cross-procedure/history scoring. Standard guests have no support-adjustment or fit-feedback UI. Research previews may record fits/does_not_fit and enum diagnostics, but these are not eligible learned rewards and must not become synthetic training observations.

Inspector is gated by the research setting and journey capability. It returns only frozen context, the seven measured structural characteristics/completeness, actual candidate feasibility, view attribution and actual client event records. Features, sampled_scores and policy are null; scoring is not_run. posterior_updates=0 is scoped to this revised API journey, not a claim about historical V2 models. Do not fetch `/v2/policy` to fill missing revised-model evidence. Client events never establish reading or completion.

## Errors, persistence and known gaps

Custom errors use `detail={code,message,...}`. Validation errors remain FastAPI 422 detail lists. Handle both. Key codes: guidance_api_disabled (404), research_preview_disabled (403), unknown_session/procedure/journey (404), invalid_capability (403), context_revision_changed, legacy_hard_requirements_unresolved, no_feasible_configuration, hard_requirements_changed, inactive_view, event_id_reused (409), infeasible_configuration with reasons (422), revised_policy_unavailable (503). Reload settings/request fresh content after a hard-constraint change; do not render a retired inaccessible view.

Journeys freeze source, wording, context and original selection evidence. Manual views preserve parents. New publication affects new/refreshed requests, not existing journeys. SQLite stores request/event deduplication and checksums with atomic state/event writes. Restart recovery is tested. Profiles reuse the existing workspace identity service; no historical profile import or database migration occurs here.

Known limits: local demo profiles are not authenticated accounts; the research flag is a local development gate, not a production role/identity service. Only English fictional wording is published in these fixtures. Official Detailed/Disclosure/Recap/Segmentation need actual source review; Map needs adequate source completeness. No revised learned selection/update, PP2 history estimator, trained evaluation, automatic participant reward conversion, production authentication or frontend redesign was implemented. UI/mobile/screen-reader verification belongs to Claude's subsequent frontend phase.

## Exact implementation files for this phase

New backend: `service/app/guidance/frontend_contracts.py`, `frontend_presentation.py`, `frontend_runtime.py`, `frontend_api.py`, `journey_store.py`. Changed integration: `service/app/preparation/content_service.py`, `service/app/host/application.py`, `service/app/host/routes.py`, `service/app/workspace.py`. New tests: `service/tests/test_frontend_guidance_api.py`. New reproducible tools: `research/export_guidance_api_examples.py`, `research/verify_guidance_api_server.py`. Docs: this file, specification/progress updates and captured example/schema/smoke JSON under `docs/examples/frontend-api-2026-10-22/`. Earlier uncommitted content-contract/registry/fixture work remains preserved.

Existing frontend files to reuse later: `src/App.tsx`, `src/app/useWorkspace.ts`, `src/guidance-v2/WorkspaceGuidance.tsx`, `src/guidance-v2/card/GuidanceCard.tsx`, `ActionBody.tsx`, `Outline.tsx`, `FeedbackLine.tsx`, `ResearchBar.tsx`, `src/guidance-v2/ProcessMap.tsx`, `workspaceClient.ts`, and `src/api/client.ts`. Existing styles include `src/styles.css`, `src/shell/shell.css`, `src/guidance-v2/v2.css`, and `src/guidance-v2/card/card.css`. Old guidance-v2/types.ts uses incompatible summary/expanded/collapsed semantics; do not alias it to the new schema. Keep fixture.json test-only; never import it or captured examples as citizen guidance.

## Actual examples and verification

See `examples/frontend-api-2026-10-22/manifest.json` for exact request bodies and real captured JSON responses: standard guidance for all three official procedures and all four fictional examples, rich fictional previews, availability, two service-specific profile contexts, errors, actual visit receipts, earned recap and factual Inspector. These were captured from real FastAPI handlers using isolated TestClient HTTP calls, not hand-written responses. `live-server-smoke.json` separately records real uvicorn loopback execution and unchanged policy; the test process was stopped. The OpenAPI mirror contains only reachable schemas for these guidance routes; future evidence types are definitions only.

Run the new tests from repository root:

```powershell
components/c4-presentation/service/.venv/Scripts/python.exe -B -m pytest components/c4-presentation/service/tests/test_frontend_guidance_api.py -q -p no:cacheprovider
```

For broad suites use a short new `--basetemp` inside C4 to avoid Windows path-length lock failures; retain/move only your own generated test folder into ignored service/.local storage afterward. The export/smoke scripts refuse to overwrite an existing report/export directory and do not train. See the progress checkpoint for final regression totals and remaining approvals.

The ephemeral port recorded in live-server-smoke.json is no longer serving; only that test child was stopped. Use the explicit startup commands for a new sandbox.

Final verification: **258 tests passed, zero failures/skips**, one existing dependency warning; real loopback server smoke passed and its process was stopped. See FRONTEND-API-CHECKPOINT.md for exact phase files and verification scope.
