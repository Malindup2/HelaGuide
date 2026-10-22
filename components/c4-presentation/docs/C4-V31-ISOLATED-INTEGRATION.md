# C4 content 3.1: isolated integration and next steps

Status: development configuration only. The 3.0 application, its content, the trained PP1 model, checkpoints, traces and stored decisions are unchanged and remain the default.

## How to run 3.1 (separate from 3.0)
Set `C4_GUIDANCE_CONTENT_SCHEMA=c4-guidance-content-3.1` and give the runtime its own directories:
- `C4_PREPARED_CONTENT_DIRECTORY` must contain `prepared-content` and `v31`, for example `service/.local/prepared-content/frontend31-<time>/v31`.
- `C4_WORKSPACE_DATABASE` should be a new file. Do not reuse a 3.0 database.
- A policy is optional. With `C4_PP1_POLICY_ENABLED=true` the 3.1 runtime needs its own `pp1-learning` folder and only accepts a 3.1 checkpoint (see `C4-RUN-AND-REPRODUCE.md`). A 3.0 store or checkpoint is refused.

## What is versioned
| Item | 3.0 (unchanged default) | 3.1 (isolated) |
|---|---|---|
| Content schema | `c4-guidance-content-3.0` | `c4-guidance-content-3.1` |
| Action meanings | `c4-scaffolds-v3.0` | `c4-scaffolds-v3.1` (D3 now hides a separate supplement) |
| Render plan | `c4-render-plan-3.0` | `c4-render-plan-3.1` |
| Registry | `c4-prepared-registry-1.0` | `c4-prepared-registry-3.1`, its own directory; each registry refuses the other |
| Feature schema label | `c4-features-pp1-1.0-525` | `c4-features-pp1-1.1-525` (same 525 structure) |
| Feature fingerprint | `features.FINGERPRINT` | `FEATURE_FINGERPRINT31` (the action meaning is part of the fingerprint) |
| Configuration identity | `c4-scaffolds-v3.0:...` | `c4-scaffolds-v3.1:...` |
| Feasibility | `evaluate` | `evaluate31` plus a `feasibility_fingerprint` in every availability record |
| Policy manifest | `policy.manifest()` | `manifest31()`: differs in `action`, `features`, `feature_fingerprint`, `content` |

`policy.py`, `features.py`, `catalogue.py`, `content.py`, `registry.py`, `feasibility.py`, `composition.py` and `decision.py` do not import any 3.1 code (checked by a test). A 3.0 checkpoint is refused when a 3.1 manifest is expected.

## What D2 and D3 mean in 3.1
- D2 chooses the primary explanation: Concise or Detailed. It is always visible, short or fuller, and each carries every instruction, condition and qualification claim of its action. Detailed keeps everything Concise covers.
- D3 chooses only the separate reviewed supplement: shown plainly when OFF, behind More/Less when ON. If a step has no supplement there is no control.
- The exact source wording travels with each action ("What the source says"). It is a reference, never the only place an essential appears.

## Content status
- Fictional 3.1 files (`research/data/guidance/fictional-v31/`) passed the automatic claim and separation checks and an internal AI-assisted author review. That is not human, external-expert, government or independent validation.
- The earlier unreviewed drafts are kept in `research/data/guidance/fictional-v31-candidates/`.
- Official procedures have no 3.1 content and stay on source fallback (4 feasible configurations each).

## Policy status (updated)
The fresh 3.1-compatible Shared LinTS policy now exists (`policy.PolicyProfile` plus `v31_pipeline.PROFILE_31`), was trained on the 3.1 synthetic study and is wired into the runtime. See `PP1-V31-RESULTS.md`, `C4-ARCHITECTURE.md` and `C4-RUN-AND-REPRODUCE.md`. The 3.0 posterior, checkpoints and results remain untouched and cannot load into 3.1.
