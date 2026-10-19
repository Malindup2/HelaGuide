# M2B citizen wording and Guided previous-step reminders

The independent research backend adds optional `wording` to guidance and saved
presentation response envelopes. `PresentationSpec`, canonical graph, source
cards, original IDs, 64 scaffold configurations, 656 policy features and runtime
database schema remain unchanged. The team stub and shared contracts are untouched.

## Actual request flow

1. Resolve reviewed wording offline from the validated graph and writing style.
   Standard requests use the chosen standard style. Personalized requests use
   the existing requested-service familiarity/navigation thresholds; unknown
   stays plain. Wording lookup never calls a provider or updates learning.
2. The existing standard path or feasible Shared LinTS path creates guidance.
3. For adaptive guidance, capture the exact wording result and reviewed artifact
   in a separate snapshot bound to session/presentation/exposure/graph identity.
   The original database transaction still owns the policy decision. A failed
   snapshot write rolls that new decision back. A later uncertain database
   commit can leave an orphan file, but it cannot be served without its matching
   stored presentation. This is a single-process prototype, not a distributed
   transaction across stores.
4. Return the canonical spec plus its wording envelope. React validates its
   graph, slot subjects, references, origin and bounded text before attaching
   it to a client-only document property. It never changes supplied map edges.
5. Render reviewed headings, explanations and labels. Required source text,
   conditions, fees, documents, branch semantics and original prerequisite cues
   stay visible under the existing preservation rules. If a reviewed step
   explanation is used, do not duplicate the older M1 generated annotation for
   that action. Missing slots keep source-based rendering.
6. A saved adaptive presentation GET restores its captured wording, even when
   the current registry is edited or removed. It never decorates an older
   presentation retroactively. Legacy presentations without snapshots retain
   source-based rendering. Corrupt snapshots fail closed without resampling.

Existing M1 provider generation controls remain unchanged. M2B does not enable
live calls. Keep both live flags false until deliberate provider verification.
Reviewed prepared wording does not become eligible for disclosure automatically.

## Persistence

`C4_PREPARED_WORDING_DIR` retains M2A's registry location. The environment-created
server also uses `service/.local/wording-views/{feedback_mode}/`, overridden by
`C4_WORDING_VIEWS_DIR`. Use absolute override paths. Snapshot files retain the
exact reviewed artifact and a checksum; they are trusted local records, not
cryptographic evidence of authorship. Keep both asset/snapshot folders with a
backup of the local database when exact historical UI reproduction is needed.
They stay outside source commits under the existing `.local/` ignore rule.

No automatic migration or database reset is performed. Historical snapshots
may need an explicit compatibility path if a future wording recipe changes;
this milestone does not silently regenerate old displayed text.

## Previous step versus cross-visit recap

Guided mode now has a small built-in navigation reminder. It uses this exposure's
acknowledgment and ordered action-display events, not array position or inferred
completion. For a jump from action 1 to action 3, it recalls action 1. On backward
navigation it recalls the last actually displayed action. On reload it derives
the same previous visit from stored navigation events. There is no reminder
on the first viewed step or before acknowledgment, and none in Overview.

When a reviewed `action_summary` exists, show it with the previous heading.
Otherwise show only a short source-based heading. The reminder explicitly
describes information shown, not work completed. It is separate from the existing
adaptive cross-visit `previous_context_recap`, so the configuration catalogue
and its meaning remain unchanged. No extra event, policy selection or reward
is created merely by rendering the reminder.

## Verification

Backend, from `service/`:

```powershell
$env:C4_DEV_LLM_ENABLED = "false"
$env:C4_LLM_ENABLED = "false"
$env:C4_TEST_POSTGRES_DSN = ""
.\.venv\Scripts\python.exe -m pytest -q
```

Frontend, from `demo-frontend/`:

```powershell
npm.cmd test
npm.cmd run build
npm.cmd run lint
```

Restart the research backend with its existing PostgreSQL settings and live
flags off, and run the frontend as before. No package install is needed.

Manual browser checks:

- Guest guidance still shows every source requirement and has no adaptive
  acknowledgment or learning. With no reviewed bundle, source rendering is
  expected. A reviewed plain bundle appears on a fresh plain guest request.
- Request personalized Guided guidance. View the first step, then Next, Back
  and a direct step jump. The reminder follows actual viewed history. Reading
  it must not mark any action complete or request another policy selection.
- Refresh on a later Guided step. The same presentation/exposure remains and
  its reminder is derived from the saved visit history.
- Diagrams retain their supplied nodes/edges and conditional/parallel semantics.
  A missing diagram label falls back to its source label.
- Submit feedback once and refresh. The original decision attribution remains;
  wording lookup and navigation reminders create no duplicate reward.

To verify prepared text, use the M2A `template`, `validate-human`, `import-human`
and `review` commands in `PREPARED-WORDING.md`. Partial bundles are supported:
prepare only chosen headings, labels or summaries with `--allow-partial`, leave
the source packet/links intact, and review the exact wording before approval.
For a deterministic first check, use the linear procedure as a guest with plain
style. After importing/reviewing, request FRESH guidance. Existing adaptive views
remain frozen by design. Inspect the response's `wording.artifact_digest` and
the collapsed Guidance reference for provenance. The main interface uses a
small Reviewed wording badge, not a claim of live generation.

The new backend tests cover guest non-learning, snapshot recovery, legacy-state
loading, pending-review behavior, original feedback attribution, corruption and
write rollback. Frontend tests cover contract rejection, unchanged source cards,
labels/edges, saved-envelope binding, first visit, jumps, backtracking and recap
separation. These checks use fake providers and temporary stores, not API credits.
