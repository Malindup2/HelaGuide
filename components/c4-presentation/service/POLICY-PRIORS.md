# C4 M3: versioned weak priors and fresh simulation runs

This change stays inside C4. The existing 656-feature Shared LinTS policy,
feasibility rules, source content, presentation attribution and explicit reward
mapping remain in place. There is no LLM request in this workflow.

## What is implemented

`priors/pp1-provisional-v1.json` contains 12 **researcher-authored provisional
judgments with AI assistance, pending expert validation**. They are not responses
from experts or participants. Each names an existing context feature and aid,
specifies a small signed score shift, gives its rationale, and cites a source.
The source scope fields distinguish published concepts from our extrapolations.

The rationale draws on these original/publisher sources:

- [Cambridge: essential processing and learner-paced segmentation](https://www.cambridge.org/core/books/abs/cambridge-handbook-of-multimedia-learning/principles-for-managing-essential-processing-in-multimedia-learning/A9E77D0172F905AC957689D1771E2888)
- [Kalyuga et al. (2003), The Expertise Reversal Effect](https://doi.org/10.1207/S15326985EP3801_4)
- [Nielsen (2006), Progressive Disclosure](https://www.nngroup.com/articles/progressive-disclosure/)
- [Mayer, Signaling Principle](https://www.cambridge.org/highereducation/books/multimedia-learning/FB7E79A165D24D47CEACEB4D2C426ECD/signaling-principle/9E37E775874EC1D93763620B8A296DD4)

These sources motivate hypotheses, not the coefficients. Self-reported familiarity
is not objectively measured expertise. Multimedia findings do not establish the
effectiveness of this text-based interface or its diagrams. NN/G explicitly notes
tradeoffs between staged navigation and interdependent tasks. No C4 improvement,
optimal layout, calibrated probability or expert agreement is claimed.

## Numerical interpretation

The previous initialization was `A = lambda I`, `b = 0`, `mu = 0`.
The new optional prior sets `mu0[context * aid] = score_delta * sqrt(656)` and
initializes `A = lambda I`, `b = A mu0`. This accounts for the existing feature
scaling. Unspecified coefficients stay zero. Every per-term shift is bounded
to +/-0.05; total absolute shifts are bounded to 0.25 (this draft totals 0.245).
Context and aid inputs remain in [0,1], so the initial score shift cannot exceed
that bound. Posterior covariance, noise, exploration scale and feature schema
are unchanged. The prior is a weak mean preference, not synthetic feedback:
initial revision and accepted feedback count are both zero.

No special assumption is made for unknown familiarity. There is no initial
previous-context-recap preference in this draft. That aid still obeys history
feasibility. Even a nonzero prior can never bypass locks or safety constraints.

The environment-created server sets `cold_start_updates=0`, with either a loaded
prior or a neutral mean. Thus the first request by a new enabled profile uses
Thompson sampling across feasible candidates, unless constraints force one.
It is not a deterministic recommendation of the highest mean. Prior hypotheses
can be outweighed by exploration. The programmatic factory retains its legacy
default config for old experiments; supplying a prior requires cold-start zero.

Real explicit feedback still uses the original selected vector:
`A += phi phi^T / noise^2`, `b += phi (reward - 0.5) / noise^2`.
About-right is 1; need-more and too-much are 0 with direction retained separately.
No response, profile creation, browsing or refresh creates a learning reward.
This is the existing linear surrogate, not a guarantee of convergence or of a
better layout after each individual rating.

## Load and validate a prior

From `components/c4-presentation/service`:

```powershell
.\.venv\Scripts\python.exe -m app.legacy.policy_runs validate --prior .\priors\pp1-provisional-v1.json
$env:C4_PRIOR_FILE = (Resolve-Path .\priors\pp1-provisional-v1.json).Path
```

Alternatively set `C4_PRIOR_FILE` to an absolute path in the ignored service `.env`.
Shell variables take precedence. No configured file means a neutral prior.
A missing/invalid explicitly configured file fails closed. A file change that
differs from a persistent run's embedded config also fails closed; there is no
automatic reset, silent new prior or merge into existing learning.

The complete prior, including provenance, is frozen in each run and its decisions.
`GET /dev/v1/policy` reports prior version, status, SHA-256 digest, cold-start
setting, policy run ID, real feedback count and posterior revision. The digest
detects a content change; it is not an authenticated expert signature.

## Explicit fresh simulation run

Stop Uvicorn first. The CLI touches only the simulation snapshot; it does not
create/reset participant state, shared team tables or source artifacts.

```powershell
# Keep the existing C4_DATABASE_URL in this terminal.
.\.venv\Scripts\python.exe -m app.legacy.policy_runs inspect --postgres
New-Item -ItemType Directory -Force .\.local\migration-backups | Out-Null
.\.venv\Scripts\python.exe -m app.legacy.policy_runs start --postgres --prior .\priors\pp1-provisional-v1.json --backup .\.local\migration-backups\before-prior.json --expected-run POLICY_RUN_ID_FROM_INSPECT --confirm-fresh-simulation
```

For SQLite replace `--postgres` with `--sqlite PATH_TO_EXISTING_DATABASE`.
For a neutral run use `--neutral` instead of `--prior PATH` and remove the startup
`C4_PRIOR_FILE` setting. `inspect` is read-only. `start` requires an expected run
ID, so an accidental retry cannot reset the newly created run a second time.

The full original row (manifest, payload, checksum and storage revision) is
written to an exclusively created archive before the snapshot update commits.
The archive must not already exist. Failed backup or validation leaves the
database unchanged; a later database failure can leave a valid archive without
a committed reset. Keep it for diagnosis. These JSON archives contain profile
and history data and belong in ignored local storage, not in a commit.

The fresh snapshot retains profile IDs, names, enablement and current context
settings. Genuine context-change events are retained and renumbered; exposure
and navigation events are removed. Current preferences remain as explicitly
set, even if originally chosen during rehearsal. The fresh policy has a new
run ID, no decisions, no active presentations, no feedback/corrections, and no
replayed old ratings. Original wording snapshots remain on disk but are not
reachable without their archived presentation. An old presentation URL returns
404 and cannot update the new policy. Browser restoration clears a missing old
reference; explicitly request fresh guidance once after this reset.

This operation supports the exact immediately preceding M2B manifest and the
current manifest. Other schema/numerical incompatibilities fail closed. The
runtime format tag is unchanged; the strict runtime schema fingerprint and
policy config in the compatibility manifest change. No auto migration runs at
startup. Restore the original archive only with the matching old application
version/configuration; archive rollback is an offline maintenance operation,
not an ordinary user flow. Preserve `.local/wording-views` for historical views.

## Later expert validation without code edits

Copy the prior JSON to a new file and version. Record real expert evidence in
the rationale and sources, adjust/remove terms, and add terms only for existing
supported features/aids. Mark `expert_validated` only after genuine review and
provide `reviewer` and `review_reference`. Those fields record the researcher's
assertion; the software does not verify the identity or review itself.

Validate the new file, archive/start a separate simulation run explicitly, and
restart with the new `C4_PRIOR_FILE`. Do not reset a real participant study or
discard genuine observations just to replace a prior. Choosing how to compare
or transition studied runs requires an explicit research decision. New features
or a different model family would require a separately versioned code change.

## Manual verification

1. Restart backend with the selected prior file and the existing offline LLM flags.
2. Open `/dev/v1/policy`: prior version `pp1-provisional-v1`, pending-validation
   status, cold-start zero, revision zero and feedback count zero after reset.
3. Existing profiles should still be listed. Request fresh guidance; old archived
   guidance does not restore. Guest/off mode remains standard guidance.
4. Create a new enabled profile and request guidance before rating anything.
   It should receive adaptive guidance from this same policy run.
5. Submit one deliberate rating. Revision/count increase once. Refresh and
   inspect again: neither increases a second time.
6. A second/new enabled profile's fresh request uses the updated shared run.
   The selected layout may be the same; changed model revision is the evidence.
7. Stop/restart backend with the same file: run ID, counts, prior digest and
   posterior fingerprint should be preserved.

Automated tests cover bounded means, unchanged uncertainty, exact update math,
first-profile selection, shared feedback learning, idempotence, feasibility,
neutral mode, provenance validation, restart recovery, archive failure rollback,
legacy-manifest handling and blocking archived feedback. PostgreSQL integration
requires the dedicated test DSN; no tests may clear the demo database.
