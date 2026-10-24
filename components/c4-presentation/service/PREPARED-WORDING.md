# M2A reusable prepared wording

M2A adds a backend contract and local preparation tools. It does not yet change
citizen rendering. M2B will consume the resolved slots. The existing M1
`app.preparation.content_cli` command and store remain compatible and separate.

## Content contract and request order

1. Load and validate C2-shaped plan + enrichment through the existing adapter.
2. Build the canonical graph. Structural features and information volume still
   come from the original graph; prepared explanation length is never an input.
3. Build a deterministic wording manifest from the graph and writing style.
   It contains action headings, action explanations, previous-step summaries,
   labels for action/service/branch/option/parallel nodes, and explanations for
   explicit action prerequisites and service dependencies. No implicit edges
   or independence are generated. Required source cards remain protected.
4. Prepare wording independently of a scaffold configuration, session or user
   history. The key includes graph, English language, style, contract, prompt,
   schema, validation recipe and length limits. No configuration ID enters it.
   The source graph and retrieval/version data remain in the artifact.
5. Validate and save the bundle pending human review. Generation is an explicit
   operator command, never a side effect of offline resolution. Provider output
   also needs a separate model assessment, which is fallible.
6. A human checks the actual meaning and records review of the exact digest.
7. Resolve reviewed wording for the current graph/style; otherwise return
   source fallback independently for each slot. Rendering selects the relevant
   slots AFTER feasibility/policy selection, without another generation pass.

All five scaffold dimensions, 64 configurations, seven structural features,
656-dimensional policy, runtime persistence and reward attribution are unchanged.
Wording review does NOT authorize hiding supplementary content; disclosure
approval remains a separate exact-source safety decision. Summaries describe
what was explained, never prove that an action was completed.

## Storage and provenance

Default: `service/.local/prepared-wording/`, excluded by the existing ignore rule.
Override with `C4_PREPARED_WORDING_DIR` or the CLI's `--directory` option. M1 uses
its original `C4_CONTENT_DIR` and explanation artifact format. No migration of
sessions, policy runs or old presentation artifacts is required.

New bundles have explicit `human_prepared` or `provider_generated` origin.
Human content has an author reference and no invented provider records. Real
generation retains model identity and every generation/assessment response
record. A fake test provider remains named `test`. No bundled content is
automatically human-approved. Preparation/review files are trusted local assets;
review digests do not authenticate the author or official source.

## Manual checks (no API key or credits required)

Run these from `components/c4-presentation/service/`. They do not change citizen
sessions or policy state. `plan` is a dry run and makes zero provider calls.

```powershell
.\.venv\Scripts\python.exe -m app.preparation.wording_cli plan --scenario linear
.\.venv\Scripts\python.exe -m app.preparation.wording_cli list
.\.venv\Scripts\python.exe -m app.preparation.wording_cli resolve --scenario linear
```

Initially expect `wording_not_prepared` and `source_fallback`. The frontend is
expected to look the same until M2B. Check conditional and parallel as well:

```powershell
.\.venv\Scripts\python.exe -m app.preparation.wording_cli plan --scenario conditional
.\.venv\Scripts\python.exe -m app.preparation.wording_cli plan --scenario parallel
```

To prepare editorial input, choose a new filename outside Git or inside `.local`:

```powershell
.\.venv\Scripts\python.exe -m app.preparation.wording_cli template --scenario linear --author local-author-1 --output "$env:TEMP\c4-linear-wording.json"
```

Open that file in VS Code. The source packet is the review reference. Fill each
`draft.items[].text`; do not change source, slot IDs, source references or quotes.
The character limits are heading 120, label 100, summary 400, explanation 1800,
prerequisite explanation 800. Empty text is intentionally invalid. Templates
are not mock provider responses or usable approved content.

```powershell
.\.venv\Scripts\python.exe -m app.preparation.wording_cli validate-human --scenario linear --input "$env:TEMP\c4-linear-wording.json"
.\.venv\Scripts\python.exe -m app.preparation.wording_cli import-human --scenario linear --input "$env:TEMP\c4-linear-wording.json"
.\.venv\Scripts\python.exe -m app.preparation.wording_cli list
```

To submit only some slots, remove other items from `draft.items` and explicitly
add `--allow-partial` to validation and import. Uncovered slots retain original
fallback wording. Nonempty submissions must keep manifest order and exact links.
Correcting a pending bundle requires `--replace-pending`; reviewed bundles cannot
be overwritten by generation/import. Changed source/style produces a new key.

After actually checking every submitted item against the source:

```powershell
.\.venv\Scripts\python.exe -m app.preparation.wording_cli show KEY
.\.venv\Scripts\python.exe -m app.preparation.wording_cli review KEY --reviewer local-review-1 --confirm-source-check
.\.venv\Scripts\python.exe -m app.preparation.wording_cli resolve --scenario linear
```

The final command should report `human_prepared` for reviewed slots. Run it again
in a fresh process to verify durable retrieval. No provider is needed. Do not
approve material simply because mechanical validation succeeds: exact references,
quotations and numeric checks cannot prove meaning, negation or completeness.

## Live provider preparation (optional, not yet live-verified)

The normal C4 provider adapter is reused. Configure the key locally without
sharing it, and enable BOTH `C4_DEV_LLM_ENABLED=true` and `C4_LLM_ENABLED=true`.
The CLI refuses live calls without the additional confirmation flag:

```powershell
.\.venv\Scripts\python.exe -m app.preparation.wording_cli generate --scenario linear --max-batches 8 --confirm-live-request
```

Use `plan` first to see the batch count. Each batch contains at most eight
targets, up to 60 KB of referenced source, and costs one generation plus one
assessment call. The default eight-batch budget is checked before any call.
Generation is all-or-nothing: a rejected or failed batch does not save an
incomplete bundle. Larger valid procedures can use an explicitly larger budget;
a single oversized target is rejected before calls. Provider failure diagnostics
are safe codes, not credentials or raw error bodies. No retry loop is added.

A valid saved bundle is still pending review. Existing bundles avoid repeat calls
unless unreviewed replacement is explicitly requested. Reviewed wording can be
used offline irrespective of the currently configured provider: its original
provider identity remains recorded, rather than becoming part of the user request.
Turn both live gates off again for the demonstration.

## New procedures and verification

All source-dependent commands accept `--plan PATH --enrichment PATH` instead of
`--scenario`. They use the same actual intake validator and graph builder. Import
compares the editorial source against that independently loaded current input;
editing a source packet does not silently change the accepted procedure.

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_prepared_wording.py tests/test_reviewed_content.py tests/test_explanations.py tests/test_llm_provider.py
.\.venv\Scripts\python.exe -m pytest -q
```

These tests use temporary data and fake provider responses, never real API
credits. They do not establish real provider success, source authenticity or
citizen comprehension. M2B and later evaluation must verify those separately.
