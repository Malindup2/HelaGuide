# C4 preparation bridge — 2026-10-21

## Runtime and safety

The existing integrated application remains `app.workspace:app`. No policy/encoder/schema migration is required. The 515 feature encoder and Shared LinTS kernel are unchanged. Existing V1, standalone V2 and integrated snapshots were not migrated or reset. Restart only when ready to use the new code; no running application was restarted during this implementation.

Completeness now uses the actual `prerequisites` and `service_dependencies` fields, with missing/partial/unknown categories failing closed. Guided browsing requires complete action/condition/branch/prerequisite/service-dependency coverage. A Full Map additionally requires complete parallel coverage. The existing official examples declare parallel coverage unknown, so new requests offer Inline support but no Full Map. Historical frozen views are not rewritten.

## PP1: no live generation (default)

From `service/`, use the existing integrated startup commands with:

```powershell
$env:C4_WORKSPACE_CONTENT_MODE = "demo"
$env:C4_LLM_ENABLED = "false"
$env:C4_DEV_LLM_ENABLED = "false"
```

Demo is the default content mode. Even if `C4_LLM_ENABLED` was left true, demo mode never starts the generation worker. Prepared backend wording and source-preserving fallbacks continue to be used; mock labels are not promoted to independently reviewed official wording. Missing Expanded variants remain infeasible.

## Explicit offline preparation mode

Only enable this when authorized to send verified source packets to the configured provider. It processes both newly registered procedures and compatible queued backlog. No live call was executed during implementation.

```powershell
$env:C4_WORKSPACE_CONTENT_MODE = "prepare"
$env:C4_LLM_ENABLED = "true"
# Configure OPENAI_API_KEY through your existing local secret setup; never commit it.
# Start the same app.workspace:app on 8018 with your chosen workspace database.
```

Startup and POST `/workspace/procedures` enqueue missing wording. Registration wakes a background thread; it does not wait for LLM completion. Each job includes an immutable canonical graph and verified relationship overlay. The provider receives both; its response schema contains only wording variants, not graph edges. Generation cannot publish.

Job JSON files remain beside the selected workspace database under `preparation/`. A separate `preparation/processing.sqlite3` owns job status and pending drafts. The policy database is never used as the queue database. Existing legacy job JSON files are read without rewriting them. Equivalent old/new requests deduplicate by graph, overlay and missing slots. JSON enqueue is atomic. This is a local durable worker, not a distributed job service.

States: queued -> processing -> pending_review; failures -> failed; outdated jobs -> stale. Published reviewed registry content reconciles jobs to published, including after restart. OS job locks prevent simultaneous workers or retry from duplicating an in-flight provider call. An abruptly interrupted processing job remains inert until explicit retry; the OS lock must be free. Failures never retry automatically. This avoids silently repeating paid requests after an ambiguous crash.

The existing generation bounds remain: 12 actions and a 100 KB source packet. Larger procedures require bounded preparation or manual authorship. Queue I/O errors do not interrupt citizen guidance. The existing provider uses a bounded timeout; shutdown waits for the in-flight call before closing the runtime.

## Operator inspection, review and publication

These are local research operator endpoints, not authenticated production moderation APIs:

- GET `/workspace/preparation`: registry missing-slot status.
- GET `/workspace/preparation/jobs`: durable jobs and generation-enabled status.
- GET `/workspace/preparation/jobs/{id}/draft`: pending draft (never citizen guidance).
- POST `/workspace/preparation/jobs/{id}/retry`: explicitly requeue a failed/interrupted job.

Save a pending draft for review:

```powershell
$jobs = Invoke-RestMethod http://127.0.0.1:8018/workspace/preparation/jobs
$job = $jobs | Where-Object status -eq "pending_review" | Select-Object -First 1
$draft = Invoke-RestMethod "http://127.0.0.1:8018/workspace/preparation/jobs/$($job.id)/draft"
# Choose a new filename under .local/v2/workspace/review/ and save without overwriting an existing artifact.
```

The CLI accepts the exact queued graph even when the procedure exists only in workspace registration state:

```powershell
# Substitute actual queued JSON, draft and unused output paths.
.\.venv\Scripts\python.exe -m app.preparation.overlay_drafts review --job .local/v2/workspace/simulation/preparation/JOB_FILE.json --input .local/v2/workspace/review/draft.json --output .local/v2/workspace/review/reviewed.json --reviewer YOUR_SOURCE_REVIEWER --confirm-source-check
```

`template` and explicitly confirmed `generate` also accept `--job` instead of `--procedure`. Templates preserve verified relationship structure. Review requires complete variant coverage, a matching source fingerprint and named non-pending reviewer. Mock artifacts cannot be relabelled reviewed. Automated reference validation does not establish semantic entailment: inspect all generated titles, diagram labels (shared action titles), explanations, qualifiers and source claims before approving.

After review:

```powershell
$artifact = Get-Content .local/v2/workspace/review/reviewed.json -Raw | ConvertFrom-Json
$body = @{artifact=$artifact} | ConvertTo-Json -Depth 100
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8018/workspace/procedures/PROCEDURE_ID/wording" -ContentType "application/json" -Body $body
```

Only this reviewed publication path changes active wording. Pending/changed artifacts, wrong sources, incomplete variants and relationship changes are rejected. Newly requested guidance uses published wording; existing documents/decisions remain frozen. Publication does not update LinTS. Real production deployment still needs authenticated editorial roles and operational monitoring.

## Verification

Tests use fake providers and newly isolated C4 test stores. Coverage includes completeness categories, unknown parallel coverage, demo-disabled execution, dynamic registration, actual background execution, pending rejection, job-based CLI review, publication, fresh guidance/restart, immutable source/relationships, failure without automatic retry, stale jobs, two-worker locking and explicit interrupted-job recovery. No live provider response or human semantic review is claimed by these tests.

Final checks: **387 backend passed, 24 skipped** (external PostgreSQL DSN unavailable), one existing Starlette/httpx warning. **142 frontend passed**. C4-only boundary and unchanged policy implementation verified; all three existing policy fingerprints/update counts matched their pre-change values. No real provider request or production editorial review was executed.
