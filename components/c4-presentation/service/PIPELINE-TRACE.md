# M4A: read-only pipeline trace API

This milestone adds a research API, not the M4B visual Inspector. It uses the
existing independent C4 runtime. There is no database migration, model reset,
new presentation selection or LLM call. Existing `/inspector` responses remain
unchanged. No C1/C2/C3, gateway, shared stub or citizen UI code is changed.

## Endpoints

`GET /dev/v1/sessions/{session_id}/pipeline-traces`

Lists this session's saved adaptive presentations in recorded offer order.
Each entry includes original IDs/configuration/selection revision, whether it
has a display acknowledgment and whether feedback was accepted. The index also
reports **current** standard/adaptive routing. A disabled profile can retain
historical adaptive presentations even though its current routing is standard.

Standard/guest guidance is not saved as a policy episode. The index explicitly
reports `standard_guidance_history: not_persisted_no_policy_or_learning_record`.
It never reconstructs a standard view using today's settings or calls the
standard renderer. Existing graph/catalogue endpoints can inspect current input,
but those must not be presented as a historical standard-guidance execution.

`GET /dev/v1/sessions/{session_id}/presentations/{exposure_id}/pipeline-trace`

Returns schema `c4-pipeline-trace-1.0` for an existing saved adaptive presentation.
The session must own that presentation. Unknown or mismatched references return
404. Session matching is an internal prototype boundary, not account authentication.
This remains a localhost research application.

Both endpoints send `Cache-Control: no-store`. All runtime reads happen under
the existing lock and storage-revision check. They do not call `change()` or
save a snapshot. A corrupted wording sidecar or inconsistent score join fails
closed with the existing 503 state-store response, without resampling.

## Reading the response

`records` holds original typed records:

- `policy_offer`: original context, seven source-based measurements, feasibility,
  complete frozen prior/configuration, candidate scores, selected phi, parameter
  draw, seed and numerical/schema versions.
- `presentation`: original graph, evidence/provenance, source cards, explanation,
  layout, diagram, visibility and recap declaration.
- `wording`, `wording_artifact`, `wording_style`: validated historical wording
  resolution and available frozen artifact, including origin and review/provider
  provenance. No lookup in today's prepared-wording registry occurs. A missing
  sidecar is reported as unavailable, not silently reconstructed or claimed to
  prove historical absence. Existing source-rendering behavior is preserved.
- `acknowledgment`, `navigation_events`: original display records for this exposure.
- `feedback`, `correction`: original accepted rating/receipt and separate optional
  diagnostic reasons/application. Before these exist, fields are null.

The other sections are projections of those records:

| Section | Meaning |
|---|---|
| `input` | Graph fingerprint check and counts; raw Plan/enrichment payloads and historical validation events explicitly unavailable |
| `structural_features` | Seven measurements in schema order, preserving observed values, completeness, normalization and nullable exact values |
| `content` | Recorded explanation origin/assurance/cache flag, diagnostics, item counts and historical wording status |
| `candidates` | Original catalogue decisions joined to original scores; rejected configurations have null score and `not_scored` |
| `selection` | Original prior/version/digest, selection mode/reason/revision and derived named context encoding |
| `display` | Derived latest displayed action/list/count, with acknowledgment interpretation |
| `learning` | Recorded reward/resulting revision and derived original-vector update deltas; no feedback means no update values |
| `current` | Current session settings, profile routing, shared run/revision/fingerprint and display staleness, separate from historical context |
| `evidence_boundaries` | Explicit recorded/derived/unavailable qualifications and locations |

No validation timestamp is invented. A Plan-generated or source-retrieval date
is not a C4 validation timestamp. A canonical graph is not a source-authenticity
certificate. Synthetic fixtures remain synthetic; other supplied sources retain
their unverified status.

Scores and uncertainty come from the **saved decision**, not from scoring the
same candidates again with today's model. Rejected choices have no fabricated
zero, probability or rank. Cold-start and forced decisions can contain recorded
posterior moments but have no sampled scores; their status is
`recorded_moments_not_sampled`. A Thompson decision uses
`recorded_thompson_score`. Linear scores are not calibrated probabilities.
The trace does not invent a causal explanation of why a feature caused a choice.

Artifact provider-call metadata describes artifact creation. It does not imply
that the provider was called for the selected view or during a trace read. A
cache flag is shown as recorded rather than inferred. No API keys or environment
variables are included by this endpoint.

## Three different model revisions

An offer may be selected at revision 0, receive delayed feedback after someone
else's update (resulting in revision 2), and be inspected when the shared model
is already at revision 3. These are distinct:

- `selection.selection_posterior_revision`: original decision revision.
- `learning.resulting_posterior_revision`: this feedback receipt's recorded result.
- `current.shared_posterior_revision`: current shared state at the trace read.

`learning.revision_immediately_before_update` is derived as the receipt's
resulting revision minus one, not copied from the selection revision.
For accepted feedback, `precision_rank_one_scale = 1/noise^2` and
`linear_delta_b = original_phi * (reward - 0.5)/noise^2`. The rank-one precision
update is `scale * outer(original_phi, original_phi)`; a dense 656-by-656 matrix
is intentionally not duplicated in every API response. The exact original phi
is available in the saved decision. Historical parameter snapshots immediately
after each update were not separately stored and are not fabricated from today's
posterior. Diagnostic reasons/preferences do not create another reward.

Display acknowledgments are client reports of visible content. They are not
proof of reading, comprehension, procedure completion or eligibility. The
presentation declaration is separate from evidence that content was displayed.

## Manual verification

Start the backend with the **same M3 settings**, including `C4_PRIOR_FILE` and
the two disabled LLM flags. Keep the same PostgreSQL simulation database. Do not
run the fresh-run command for M4A. The frontend can use its existing startup
command, but has no new trace UI until M4B.

In a separate PowerShell terminal:

```powershell
$traceBase = "http://127.0.0.1:8016"
$traceProfiles = Invoke-RestMethod "$traceBase/dev/v1/demo-profiles"
$traceProfiles | Select-Object display_name, session_id

# Choose a profile that already has adaptive guidance history.
$traceSession = [Uri]::EscapeDataString($traceProfiles[0].session_id)
$traceIndex = Invoke-RestMethod "$traceBase/dev/v1/sessions/$traceSession/pipeline-traces"
$traceIndex.presentations | Select-Object exposure_id, selection_posterior_revision, acknowledged, feedback_accepted

# If the list is empty, choose another profile or explicitly request guidance in the UI.
$traceExposure = [Uri]::EscapeDataString($traceIndex.presentations[-1].exposure_id)
$traceUrl = "$traceBase/dev/v1/sessions/$traceSession/presentations/$traceExposure/pipeline-trace"
$traceResult = Invoke-RestMethod $traceUrl
$traceResult.selection | Select-Object prior_version, prior_status, selection_mode, selection_posterior_revision, feasible_count, rejected_count
$traceResult.display
$traceResult.learning | Select-Object status, reward, selection_posterior_revision, revision_immediately_before_update, resulting_posterior_revision
$traceResult.current | Select-Object shared_policy_run_id, shared_posterior_revision, accepted_feedback_count

# With no simultaneous UI interaction, repeated reads must not change learning.
$traceBefore = Invoke-RestMethod "$traceBase/dev/v1/policy"
$null = Invoke-RestMethod $traceUrl
$null = Invoke-RestMethod $traceUrl
$traceAfter = Invoke-RestMethod "$traceBase/dev/v1/policy"
$traceBefore.posterior_fingerprint -eq $traceAfter.posterior_fingerprint
```

The last comparison should be `True`. You may paste `$traceUrl` into the browser
to inspect the full JSON. Saved records/scores should remain the same after a
backend restart with the same configuration. A later genuine feedback update
may change `current` and the newly accepted feedback sections, not the original
selection context, graph, candidates or scores.

## Verification coverage

Tests assert exact equality with existing saved presentation/Inspector records,
all 64 feasibility entries, null rejected scores, distinct selection/update/current
revisions, original-vector update math, neutral/forced/cold-start modes, current
context changes, catalogue changes, guest/disabled routing, session ownership,
partial/unknown completeness, frozen wording provenance, corruption handling,
and restart recovery. Repeated-read tests prohibit selection, evaluation,
generation, learning, wording capture and database writes; they also compare
snapshot rows, sampler state, provider-call counts and wording file bytes.

Runtime-state models are unchanged, so the M3 storage compatibility manifest is
unchanged. These trace models are response-only. They should remain outside
persisted runtime models as M4B adds its UI.
