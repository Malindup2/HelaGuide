# Prepared-first content and asynchronous preparation checkpoint

Date: 2026-10-22. Controlled content phase on c4/scaffolding-dimensions; no commit/push or runtime cutover.

## What works now

The existing app.workspace application has an explicitly opt-in content service, not another application. Neutral app/guidance modules resolve registered validated sources, reuse compatible publications, return complete source fallback and enqueue cache misses into the existing PreparationProcessor through a schema handler. This reuses its SQLite queue, claim/OS lock, background thread, retry rules, failure handling and draft inspection; there is no second queue implementation.

Compatibility key: procedure + graph fingerprint + relationship fingerprint + language + content schema. Content version/fingerprint and exact review remain stored on immutable artifact records. Jobs deduplicate across requests and worker instances. Cache hits do not enqueue or construct a provider. Missing/invalid publications, queue failures and provider failures preserve baseline guidance. Pending/Draft content is not passed to citizen composition.

Lifecycle: pending/queued -> processing -> draft (queue status pending_review) -> explicitly reviewed -> explicitly published. A review record alone never publishes. Reviewed artifacts bind exact content and source fingerprints. Publication affects later requests only; existing journey documents remain frozen. Failed/interrupted paid calls do not automatically retry. The existing processor.retry interface requires an explicit action; no retry-on-refresh behavior was added.

Four fictional packets in research/data/guidance/fictional pass the actual draft/review/publication pipeline. The author-review is named **Codex internal fictional author-review (AI-assisted; not human or external expert review)**, with per-field source comparisons. This is not an external expert assessment or official verification. No old mock/official wording is relabelled reviewed. External assessment of the six mechanisms and scenario hypotheses remains pending and does not block this provisional demonstration.

Conditional, parallel and practice fixtures each support 96 configurations. Linear supports 48 because separate phases would simply repeat its two actions. Detailed remainders explain verified relationships; essentials remain exact-source and always visible. Stage fees stay stage-scoped, including the three fee mentions in the registration source paragraph. No amounts, facts, edges or totals were invented. Reviewed headings are reused as map labels; map data is copied from the source graph/validated overlay.

## Deliberately inactive boundaries

Default C4_PREPARED_CONTENT_ENABLED=false preserves normal checkpoint behavior. When enabled, ordinary workspace guidance performs the existing identity-authorized request and adds a separately labelled prepared_content result. The top-level frozen V2 document, 515 feature selection and frontend renderer are unchanged. /workspace/content/guidance is a backend content-verification preview, explicitly labelled content_preview_no_learning, not a contextual policy decision. It cannot serve as evidence of revised-policy learning.

The revised encoder, history estimator, statistical settings, training and frontend integration are not implemented. The new registry is not migrated from either old store. Live provider connectivity has not been executed: generation integration tests use offline providers. Semantic entailment, correct translation and authentic human editorial identity still require review; schema/coverage checks cannot prove those properties. The local editorial CLI is not an authenticated production editorial service.

## Configuration

| Setting | Demo verification | Authorized dynamic preparation |
|---|---|---|
| C4_PREPARED_CONTENT_ENABLED | true | true |
| C4_PREPARED_CONTENT_MODE | demo | dynamic |
| C4_PREPARATION_ON_MISS | false | true |
| C4_LLM_ENABLED | false | true |
| C4_DEV_LLM_ENABLED | false | false |
| C4_WORKSPACE_CONTENT_MODE | demo | demo (old generator disabled) |

All three dynamic mode/on-miss/LLM gates must permit generation. DEV_LLM_ENABLED alone grants nothing. Demo never generates even when its other generation flags are true. Conflicting legacy/revised generation is rejected rather than scheduling two schema-specific provider calls. Dynamic mode uses OpenAIExplanationProvider.from_environment and the existing OPENAI_API_KEY/C4_LLM_MODEL configuration; source packets are limited to 12 actions and 100 kB. Provider failure/truncation leaves fallback intact.

The demo installer only publishes the explicit fictional fixtures; it does not approve any official content. Dynamic mode does not automatically install demo fixtures, but can reuse previously published compatible artifacts in its selected registry. Only English fictional content is prepared here. A different language causes a separate miss; fallback remains in the supplied source language, without an unreviewed automatic translation.

## Safe opt-in backend verification commands

Do not stop or change an existing running application for this phase. Open a separate PowerShell terminal in components/c4-presentation/service and use a new sandbox on an unused port, such as 8019:

```powershell
$c4ContentRun = Get-Date -Format 'yyyyMMdd-HHmmss'
$env:C4_WORKSPACE_DATABASE = Join-Path (Get-Location) ".local\v2\workspace\content-$c4ContentRun\state.sqlite3"
$env:C4_PREPARED_CONTENT_DIRECTORY = Join-Path (Get-Location) ".local\prepared-content\content-$c4ContentRun"
if (Test-Path -LiteralPath $env:C4_WORKSPACE_DATABASE) { throw 'Choose a new sandbox path' }
$env:C4_WORKSPACE_MODE = 'simulation'
$env:C4_WORKSPACE_CONTENT_MODE = 'demo'
$env:C4_PREPARED_CONTENT_ENABLED = 'true'
$env:C4_PREPARED_CONTENT_MODE = 'demo'
$env:C4_PREPARATION_ON_MISS = 'false'
$env:C4_LLM_ENABLED = 'false'
$env:C4_DEV_LLM_ENABLED = 'false'
.\.venv\Scripts\python.exe -m uvicorn app.workspace:app --host 127.0.0.1 --port 8019
```

No new frontend run command is required: the frontend is deliberately untouched and does not consume the revised prepared_content field yet. Verify JSON in a second terminal:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8019/workspace/content/status'
$body = @{
    procedure_id = 'synthetic-practice-v2'
    configuration = @{
        navigation='guided'; explanation='detailed'; disclosure='on'
        relationships='map'; recap='on'; segmentation='on'
    }
} | ConvertTo-Json -Depth 5
$result = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8019/workspace/content/guidance' -ContentType 'application/json' -Body $body
$result | Select-Object content_state, review_kind, generation_enabled, selection_origin
$result.document | ConvertTo-Json -Depth 20
Invoke-RestMethod 'http://127.0.0.1:8019/workspace/content/jobs'
```

Expected: published fictional artifact, internal_fictional_author review, generation disabled, rich render plan, no cache-hit preparation job. The selection_origin explicitly identifies a non-learning preview.

For dynamic preparation later, deliberately restart this sandbox with dynamic/true/true settings from the table and authorized provider credentials. Do not enable it during PP1. Generation was not enabled against a live provider in this phase.

## Research preview and explicit review/publication

- POST /workspace/content/guidance: prepared-first resolution and fallback. An infeasible preview request reports reasons and returns baseline content instead.
- GET /workspace/content/status: effective gates and schema.
- GET /workspace/content/jobs: durable queued/processing/failed/pending_review/published states.
- GET /workspace/content/jobs/{id}/draft: explicitly provisional researcher JSON, never published citizen content.
- Existing POST /workspace/sessions/{session_id}/guidance: optional preflight/additional prepared_content field after identity/revision validation; existing document/decision remain unchanged.

Worker draft JSON includes artifact_id. Job source snapshot is <content-directory>/v2/jobs/<job-id>.json. A reviewer must inspect the complete source and draft, then prepare a reviewed-content JSON with field-level checks and reviewer/date/scope/evidence plus the exact GuidanceContent fingerprint. The CLI does not fill in review results on the reviewer's behalf:

```powershell
.\.venv\Scripts\python.exe -m app.guidance.editor inspect --directory "$env:C4_PREPARED_CONTENT_DIRECTORY" --artifact DRAFT_ID
.\.venv\Scripts\python.exe -m app.guidance.editor review --directory "$env:C4_PREPARED_CONTENT_DIRECTORY" --artifact DRAFT_ID --source-job JOB_JSON --reviewed-content REVIEWED_JSON --reviewer 'Actual reviewer name' --kind human_source_fidelity --confirm-source-review
.\.venv\Scripts\python.exe -m app.guidance.editor publish --directory "$env:C4_PREPARED_CONTENT_DIRECTORY" --artifact REVIEWED_ID --source-job JOB_JSON
```

Review returns a new REVIEWED_ID. Publication is separate. internal_fictional_author is accepted only for synthetic graphs. If text changes during review, save it as a new draft first; a review cannot silently change the stored draft's wording. The CLI can process dynamically registered procedures because it uses the durable source snapshot, not a hardcoded procedure list. These backend endpoints are local development/research interfaces, not a production authentication design.

## Storage and verification

New content ownership: <C4 content-directory>/registry.sqlite3; immutable draft/review history and current-publication index. Jobs: <content-directory>/v2/jobs/processing.sqlite3 and immutable source snapshots. Directory guard requires a dedicated prepared-content path inside C4 and refuses unrelated database schemas. No existing workspace, V1 or standalone V2 database was opened or migrated during implementation.

**Final relevant regression: 226 passed, 0 failed, 0 skipped in 26.74 s; one existing Starlette/httpx deprecation warning.** This includes 27 content-integration cases, 48 contract cases and 151 related existing preparation/graph/profile/publication checks. The new suites cover fixture publication/capabilities, actual API/cache hit and miss, asynchronous fallback, duplicate requests/workers, provider failure/no retry, malformed generated drafts, wrong fingerprints/languages, stored-artifact tampering, queue failure, explicit review CLI for dynamic registration, mode gates and unchanged guest posterior. Existing content/preparation/graph and profile/publication regression checks remain required.

## Resume / next approved integration

Read this file and UNIFIED-PROGRESS.md; inspect branch/status. Preserve current changes and all stores. Complete any genuine verification failure before broader work. Next: human official-content review as needed, then separately approved encoder/history design and later one-runtime/renderer consumption of these content capabilities. Do not activate revised action meanings under old coefficients. External expert suitability feedback can refine documented hypotheses without blocking honest fictional demonstrations. No synthetic rewards were generated in this phase.


Final boundary verification: all tracked and untracked code/doc/fixture changes are within C4. The frontend, original procedure inputs, LinTS kernels/features/catalogues and existing policy manifests have no diff. This phase changes only content/preparation integration hooks in the existing workspace/API/worker in addition to the neutral modules and fixtures. Old databases were not migrated or reset; isolated generated test stores are retained under ignored service/.local/v2/content-phase-tests-* paths. The initial new-test run exposed strict graph JSON parsing and an incorrect test workspace path; both were corrected before the passing final regression. No remaining known test failure.
