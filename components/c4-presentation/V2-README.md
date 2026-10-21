> Active integrated PP1 application: see [UNIFIED-README.md](UNIFIED-README.md). The standalone paths below are historical baseline documentation.

# C4 V2 research workspace

V2 is an additive implementation on `c4/scaffolding-dimensions`. V1 remains the default frontend route and its API, policy and databases are not migrated. Every implementation file belongs to C4.

## Run locally (PowerShell)

Backend terminal:
```powershell
Set-Location C:\Users\Lenovo\Desktop\HelaGuide\components\c4-presentation\service
$env:C4_V2_MODE = "simulation"
$env:C4_V2_SEED = "0"
$env:C4_V2_DATABASE = Join-Path (Get-Location) ".local/v2/simulation/state.sqlite3"
.\.venv\Scripts\python.exe -m uvicorn app.v2.api:app --host 127.0.0.1 --port 8017
```
Frontend terminal:
```powershell
Set-Location C:\Users\Lenovo\Desktop\HelaGuide\components\c4-presentation\demo-frontend
npm run dev -- --host 127.0.0.1 --port 5173
```
Open http://127.0.0.1:5173/#c4-v2. Inspector: http://127.0.0.1:5173/#c4-v2-inspector in the same tab. V1: http://127.0.0.1:5173/#. V2 uses port 8017; it does not use V1 port 8016. `VITE_C4_V2_API` can override the V2 API base at frontend startup.

## Action and model semantics

The catalogue is 2 navigation × 2 explanation × 2 disclosure × 3 relationships × 2 journey recap × 2 preparation summary = 96 nominal configurations. Capability and user lock filtering precedes selection. A sole feasible candidate is explicitly marked forced. Feasibility never falls back by relaxing constraints.

Explanation chooses reviewed core instruction wording. Disclosure affects only separately approved, fact-free optional passages. Four combinations remain independent. Conditions, required facts, prerequisites and conditional joins remain available regardless of optional aids. Route focus is a browsing preference, not an eligibility decision. Guided Next follows the focused route when selected; all route alternatives remain accessible. Recap uses earlier actions viewed in this journey and never asserts completion.

The feature vector has 416 context × action terms, 35 user × complete-structure terms, 55 targeted triples and 9 scaffold pairs: 515 total. Rating 5 is the reference contrast; unknown has its own indicator. Complete-only interaction values are zero for partial/unknown structure, while observed values and missingness flags remain available. Each block is bounded/scaled before the final vector is divided by two; the norm is checked at runtime. The action intercept retains context main effects. Structural normalization reuses C4's bounded measurement definitions; conditional joins are counted once and longest supplied paths include conditional leaves without asserting all alternatives are required.

The existing `_GaussianPosterior` is reused unchanged. A single joint Gaussian coefficient draw scores all feasible candidates, and the maximum sampled score wins. Rewards retain the centered linear update from V1: about-right=1, need-more=0, too-much=0. Scores are not calibrated probabilities. Initial precision/noise/exploration are 1 with zero coefficient mean (reward baseline .5). There is no profile rule selecting a configuration. Broad individual-history effects are deliberately excluded; PP2 score adjustment always abstains.

Action, feature, scaling fingerprint, prior parameters, origin and encoder variant are persisted in the model manifest. Incompatible state is rejected. Ablations preserve common feature scaling: pairwise=416, threeway=506, full=515. V1 coefficients must never be imported. A future changed prior or encoding requires a separate store and manifest version.

## Data and source preparation

The shared Plan v1 is read without modification. `research/data/v2/<example>/` may contain `plan.json`, existing C4 `enrichment.json`, and a graph-bound `overlay.json`. Duplicate procedure identities, unresolved references, cyclic dependencies, unsupported optional collapse and conflicting parallel prerequisites fail validation. Overlay ownership denotes verified action responsibility; a service agency alone is not represented as an action owner. Conditional expressions support AND, OR and selection of a supplied route. No unsupported official relationships are generated.

The six existing procedures retain their bounded sources. The additional practice application is explicitly fictional and demonstrates all six supports, alternative copy routes, parallel preparation, a conditional join and several fictional desks. Existing official snapshots use source-preserving concise instructions until expanded wording has been explicitly reviewed. Their coverage limits remain visible. They are not full current government workflows or legal guidance.

Content preparation is offline, never in the citizen selection request. `python -m app.v2.preparation --help` describes template, generate and review commands. Generation uses the existing structured provider interface and requires an explicit live-call flag. It produces pending content, never automatic approval. Review requires a named reviewer and explicit source-check flag. Put approved JSON artifacts in `research/data/v2/approved/`; registry loading checks the exact graph and artifact checksum. Structural metadata is retained when generating from an existing overlay. A checksum protects integrity, not factual entailment: human review must check every requirement, exclusion and explanation. No live LLM call is required for the demo.

## Evidence and privacy

A journey has a capability token held in tab-scoped session storage; only its hash is stored on the backend. Do not publish tokens. Run on loopback. This is a local research service, not authenticated participant hosting.

Events bind journey, decision, view, graph/content fingerprints, server sequence and timestamp, client timestamp, opportunity and origin. Visibility comes from IntersectionObserver. Control opportunities are distinguished from applicability. Opening details and navigating are neutral activity, not rewards or proof of completion. Direct adjustments create child views; feedback on any adjusted view never updates the original policy, including an undo to the original configuration. Exact duplicate events and ratings are idempotent; conflicting reuse is rejected. Events do not contain free-text personal responses. A transient network failure retries the identical event identity once; persistent errors are shown. No offline delivery guarantee is claimed.

SQLite transactions atomically save feedback, posterior receipt and complete research state. Reload replays accepted updates and verifies the posterior fingerprint; RNG state is also restored. Concurrent stale writers fail explicitly. Simulation and participant modes reject each other's manifests and must use separate paths. State is a complete JSON snapshot per transaction: appropriate for bounded research runs, not a production-scale event warehouse. Retention/deletion policy and authenticated consent are external deployment requirements, not implemented participant governance.

## Synthetic training and evaluation

From the service directory:
```powershell
.\.venv\Scripts\python.exe -m app.v2.simulation --output .local/v2/experiments/pp1-seed17 --seed 17 --train 120 --evaluation 60
```
The output directory must be new, inside C4 and contain a `v2` path component. Each encoder runs actual select → display → rating → posterior update. The seeded synthetic outcome generator is separate from selection. Records include configurations, contexts, outcome probabilities, sampled uniforms, receipts, held-out evaluation and reload evidence. Held-out procedure and familiarity/confidence ratings differ from training; null and burden regimes are included. Compare minimal, rich, uniform and encoder ablations. Oracle regret is defined only against the declared synthetic generator. These results do not validate benefit for real citizens. Repeating a seed in a new output directory reproduces selections/outcomes and posterior fingerprints; UUIDs and wall-clock timestamps intentionally differ.

To demonstrate a trained full model, stop only the V2 backend and set:
```powershell
$env:C4_V2_SEED = "17"
$env:C4_V2_DATABASE = Join-Path (Get-Location) ".local/v2/experiments/pp1-seed17/full.sqlite3"
.\.venv\Scripts\python.exe -m uvicorn app.v2.api:app --host 127.0.0.1 --port 8017
```
Use a fresh browser session/journey because capability tokens belong to the previous store. For an immutable experiment record, copy the V2 experiment directory to a separate V2 demo directory while the process is stopped and run the copy. Never point this API at a V1 database.

## PP1 demonstration: 2.5 minutes

- 0:00–0:20: State the hypothesis: appropriate support depends on current familiarity/confidence and supplied procedure structure; extra support can also burden users. Identify all training shown as synthetic.
- 0:20–0:55: Request the fictional practice procedure with current context. Show the actual selected configuration. Compare a simple collect-pack procedure with the branching/parallel practice procedure. Selection may differ; do not promise a predetermined arm.
- 0:55–1:25: On the original view, expose an action and rate support fit. Open Inspector to show sampled candidate scores, selection revision and the genuine posterior increment. This is evidence of learning mechanics, not human effectiveness.
- 1:25–2:05: Return to guidance. Change explanation without changing optional disclosure, toggle the map and summary, browse an action and open earlier-step recap. Show route grouping and the conditional join. Label this as user adjustment.
- 2:05–2:20: Rate the adjusted view and show the no-policy-update receipt. Required conditions and documents remain.
- 2:20–2:30: Explain persistence, synthetic evaluation limits, and future PP2 history transfer with uncertainty-controlled abstention.

## Verification commands

From service:
```powershell
.\.venv\Scripts\python.exe -m pytest -q -rs --basetemp=.local/v2/verification-temp
```
From demo-frontend:
```powershell
npm test
npm run build
npm run lint
```
Use a fresh test-output directory if preserving a previous temporary test snapshot matters. See V2-PROGRESS.md for executed results and outstanding verification.

## File ownership and integration

Backend modules: catalogue, features, content, measurements, runtime, api, preparation, fixture/export_fixture and simulation under `service/app/v2/`. Frontend: `src/guidance-v2/`; `src/main.tsx` mounts the additive route. `GuidanceMessage` consumes a frozen document/view and callbacks and can later be embedded in the team's chat. External routing/authentication, live C2 delivery and shared chat integration remain team integration work. The current C4 adapter already accepts Plan v1 with C4-owned enrichment, so no shared schema changes are needed for local research.
