# C4 visual Pipeline Inspector (M4B)

Run the existing backend on 127.0.0.1:8016 and the demo frontend on 127.0.0.1:5173. Open `http://127.0.0.1:5173/#pipeline-inspector`, or use **Pipeline Inspector** in the citizen header. The header link opens a separate tab. No additional dependency or server is required.

The Inspector route mounts separately from the citizen workspace. It never mounts the workspace/session/GuidanceEpisode effects. Its API adapter exposes only profile-list, trace-index and trace GET operations, using the existing no-store transport. It does not create sessions, select configurations, acknowledge display, send navigation, submit ratings, apply preferences, generate wording, or reset/repair storage. There is no polling. Local session/profile association is not authentication.

## Inspect a recorded presentation

1. Choose a saved demo profile or enter an existing `guest:<32 hex characters>` session ID. Disabled profiles can still have adaptive history.
2. The latest saved adaptive presentation is opened initially. Choose any other saved exposure from the presentation selector.
3. Inspect the numbered pipeline links: canonical graph/sources, seven qualified measurements, original context, all 64 candidate evaluations, original selection/prior, content provenance, acknowledged display, attributed learning and evidence boundaries.
4. **Refresh saved records** reads the same exposure and updates its feedback/current-state projection. The hash preserves session and exposure across browser refresh. Missing/deleted exposures are reported, never silently replaced by another presentation.

Standard requests have no persisted policy/exposure/learning trace. An empty history is shown honestly; the Inspector does not request adaptive guidance to populate it. Use the citizen workspace separately if a new decision is needed.

## Interpretation

- Pipeline steps are conceptual sections of stored evidence, not a timed execution trace. Raw upstream payloads and historical validation events are unavailable.
- Service dependencies, action prerequisites, branch membership and explicit parallel groups are kept separate. Graph inspection adds no relationships or completion claims.
- Partial/unknown feature coverage retains null exact values. The UI shows observed values and completeness separately.
- Rejected candidates remain unscored. Forced/baseline selections can have moments but no Thompson sample. Values are linear surrogate scores, not probabilities or feature importance. All five scaffold dimensions remain visible.
- Selection revision, revision immediately before/after accepted feedback and current shared revision are separately labelled. Missing feedback is not reward zero. Corrections are not extra rewards.
- Frozen content origin, assurance, diagnostics and wording snapshots are shown without claiming a live LLM call. Legacy missing snapshots remain unavailable. Provisional priors remain labelled pending expert validation.
- The Inspector does not render citizen ActionSections, observers or FeedbackPanel; reading it cannot ACK a presentation. The complete JSON is available in an expandable reference.
- Switching session/exposure clears the previous trace immediately. Generation tokens discard late requests; failed reads display an error rather than the old trace. Malformed/version-incompatible and attribution-inconsistent responses fail closed.

## Verification

Run `npm.cmd test`, `npm.cmd run build`, and `npm.cmd run lint` from demo-frontend. The synthetic fixture was produced by the backend's isolated TestClient using a temporary SQLite database, an offline fake provider, and two explicitly submitted test ratings. It contains no demo or participant records. Tests cover real response parsing, identity/schema/candidate validation, null semantics, GET-only requests, refresh/deep links, absent history, errors, stale response isolation and evidence rendering.

Manual check with the persistent demo backend:

1. Note `/dev/v1/policy` revision, accepted feedback count and posterior fingerprint.
2. Open the Inspector in a separate tab, select a profile/exposure, filter candidates, expand records, change exposure, and refresh both the records and browser. The selected exposure should survive browser refresh.
3. A rejected candidate must show rejection reasons and **Not scored**. A missing rating must show **No accepted reward**. Older selections may differ from the current shared revision.
4. Repeat the policy read with no simultaneous citizen interaction. Revision/count/fingerprint must remain unchanged.
5. In the citizen tab submit one deliberate eligible rating. Refresh that exposure in the Inspector. It should show the attributed reward and resulting update revision. Refresh again: no extra update.
6. Try an unknown session, a profile with no adaptive history, a disabled profile with older history, a stopped backend, and a narrow screen. Errors/empty states must not show a previous session's trace. Confirm keyboard access to selectors, filters, disclosures and horizontally scrollable graph/table regions.

This milestone supplies functional research inspection. Overall citizen UI polish remains a later agreed step; no PP2 interaction scorer is introduced.

Implementation verification: all 107 frontend tests, production build and ESLint passed. Browser checks against a disposable backend verified loading a saved profile, choosing an older acknowledged exposure, candidate filtering, dependency rendering and preservation of that exposure after full browser refresh. Policy fingerprint, revision and accepted-feedback count stayed unchanged during those read-only checks. The persistent demo database was not used. A StrictMode effect-replay regression found during browser verification is covered by a test.
