# M5: immediate adaptive-view adjustments and Undo

The citizen workspace now offers **Adjust this presentation** after an adaptive selection. Users can switch Overview/Guided, show/hide a structurally supported relationship diagram, expand/collapse reviewed optional source context, show/hide a previous-context recap, and show/hide prerequisite cues. All choices must belong to the original decision's feasible set. This retains structure, disclosure review, original history, hard locks and accessibility restrictions; it does not override them. Required instructions, conditions, notices, fees, documents and evidence remain in the source inventory and retain mandatory visibility.

Standard guidance keeps its existing fixed Overview contract and no learning exposure. The M5 controls apply to adaptive presentations. General UI polish and the PP2 interaction scorer are separate later work.

## Identity and learning boundaries

- The original `PresentationSpec`, `PolicyOffer`, selected feature vector, Thompson sample and policy receipt are never rewritten.
- Every explicit change receives a new `view:<uuid>` and links to its parent and root session/exposure/presentation/policy run. The view specification is a layout projection with root lineage IDs; `view_id`, not a new policy decision, identifies the manual display.
- Only frozen original content/wording is reused. Adjusting never calls the provider or adopts newly reviewed content. Source-preserving layout composition validates the new specification before committing it.
- Undo creates a new display identity restoring the prior layout. It retains older history and ratings, supports multiple adjustments/Undo operations, and requires fresh display acknowledgment for the restored view. This is not deletion or reversal of a learned reward.
- A procedural action must enter the viewport before a manual display is acknowledged. Guided revisits are recorded separately; passive navigation is never a reward or a claim of comprehension/completion.
- Manual ratings are stored against the displayed view and labelled `learning_eligible: false`. Once manual lineage exists, even ratings after Undo stay separate from policy learning: seeing an intervention can affect later judgments. Fresh guidance creates a new eligible policy selection.
- An already accepted original receipt remains immutable and idempotently retrievable. New original-policy rewards and original navigation are blocked after manual-view lineage, rather than attributing a changed presentation to the original features.
- **Save these view settings as future preferences** is a separate explicit action, only after confirmed display. It saves all five current settings as soft preferences, preserving familiarity, navigation confidence, hard locks and accessibility. It does not guarantee the same future policy choice or create a reward. A stable preference event makes retries safe; changed settings freeze the old episode for reference and require fresh guidance.

## Storage and compatibility

Policy `RuntimeState` and its compatibility manifest are unchanged; existing SQLite/PostgreSQL policy state needs no migration or reset. A separate transactional SQLite sidecar stores manual view lineage, displays and manual ratings. The environment-created backend defaults to `.local/c4-{simulation|participant}-views.sqlite3`; `C4_ADJUSTMENT_DB` can select another local file. Records are namespaced by the original policy run and root identity. Factory-created persistent SQLite runtimes default to `<policy database>.views.sqlite3`; in-memory factories keep an in-memory sidecar unless configured otherwise.

Back up and restore the policy database, adjustment database and wording snapshots together. Missing sidecar history cannot be reconstructed from the policy database; do not discard or restore an older sidecar while keeping newer policy/session data. This is the same single-backend-process local research deployment as the existing snapshot store, not a distributed service. Local profile/session matching is not authentication.

Sidecar writes use SQLite transactions, revision checks, checksums and strict schema/lineage validation. View actions, displays and ratings each retain the original expected revision and request identity. Identical retries recover the accepted state; changed bodies, stale parents/revisions and reused event identities conflict. Corrupt history blocks reads and new original-policy feedback. The frontend retains an unconfirmed request in browser storage and offers explicit retry or a read-back recovery, with no automatic mutation on refresh. The active view and latest acknowledged Guided action restore from the backend.

## API

All paths below are relative to `/dev/v1/sessions/{session_id}/presentations/{exposure_id}`:

| Method/path | Purpose |
| --- | --- |
| GET `/views` | Read lineage, current view, original feasible choices and learning eligibility |
| POST `/views` | Explicit `adjust` or `undo`, with request ID, expected view revision, parent view, focus action and optional configuration |
| POST `/views/display` | Acknowledge an actual visible action for the current manual view |
| POST `/views/rating` | Save one explicit, non-policy rating for the current acknowledged view |
| POST `/views/preferences` | Explicitly save displayed view settings as future soft preferences, with request ID and expected session revision |

Configuration request bodies contain the five input fields; `configuration_id` is computed by the backend. Reads return it for display. GET `/pipeline-trace` additionally returns an `adjustments` projection, and the Inspector exposes manual lineage separately from original display/feedback records. Existing trace fields retain their original meaning.

## Manual verification

Use the existing backend/frontend startup commands and prior settings. No new required environment variable is introduced.

1. Select an enabled demo profile and request fresh guidance. Note its original configuration and current `/dev/v1/policy` revision/count/fingerprint.
2. Show a feasible dependency/branch/parallel diagram, then hide it. Try Overview/Guided and the available recap, disclosure and cue controls. Unavailable aids must stay unavailable; instructions/conditions/fees/documents must stay present.
3. Bring an action into the viewport. Submit a rating in **How was this adjusted view?** It must confirm a separate view record, with no shared-policy update.
4. Make two adjustments, use Undo twice, and inspect **View history**. Undo must restore layouts in order while keeping a new view identity, previous records and ratings.
5. In Guided mode browse to a later action and refresh. The current adjusted layout/action should restore without reselecting or duplicating a rating.
6. Use **Save these view settings as future preferences** only if desired. The old episode becomes reference-only. Request fresh guidance and confirm the Inspector uses the updated original context while hard settings/familiarity remain intact.
7. Inspect the original exposure in Pipeline Inspector → Display → Manual view lineage. Original selection/reward remains separate from manual views and ratings.
8. Repeat policy status reads with no concurrent ordinary rating. Manual adjustments, ratings, Undo and preference application must leave its posterior/revision/accepted-policy-feedback count unchanged. A deliberate eligible rating on fresh, unadjusted guidance must still update it once.

Automated tests use disposable databases, synthetic fixtures and offline providers. They cover all feasible layouts' source preservation, conflict/retry behavior, Undo identity, direct original-endpoint guards, manual-rating separation, explicit preferences, corrupt storage and restart recovery, plus frontend contracts and retry persistence.

Browser verification used an isolated offline backend and disposable databases. Showing a dependency diagram, separate manual rating, Undo, switching to Guided, later-action navigation, full browser-refresh restoration and explicit preference saving were exercised. Posterior fingerprint, revision and accepted policy-feedback count stayed unchanged through those manual operations. Requesting fresh unadjusted guidance and submitting one explicit rating then produced exactly one normal policy update. Manual lineage was also verified in the separate Pipeline Inspector. The persistent demo database was not used.
