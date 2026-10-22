# C4 content 3.1: isolated integration and next steps

Status: development configuration only. The 3.0 application, its content, the trained PP1 model, checkpoints, traces and stored decisions are unchanged and remain the default.

## How to run 3.1 (separate from 3.0)
Set `C4_GUIDANCE_CONTENT_SCHEMA=c4-guidance-content-3.1` and give the runtime its own directories:
- `C4_PREPARED_CONTENT_DIRECTORY` must contain `prepared-content` and `v31`, for example `service/.local/prepared-content/frontend31-<time>/v31`.
- `C4_WORKSPACE_DATABASE` should be a new file. Do not reuse a 3.0 database.
- Do not set `C4_PP1_POLICY_ENABLED`. A 3.1 runtime refuses any policy at start-up.

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

## Next steps for a fresh compatible Shared LinTS model (not done here)
1. Make `features.py` accept a version: build `SPEC` with `FEATURE_SCHEMA31` and `ACTION_SCHEMA31` so the encoder produces `FEATURE_FINGERPRINT31`. Keep the 525 structure unless a research change is approved separately.
2. Add a 3.1 policy store whose manifest is `manifest31()`, in a new directory such as `service/.local/pp1-learning/v31-...`. Start from the prior; never load a 3.0 posterior.
3. Let `Flavour` for 3.1 set `supports_policy=True` only once that store exists and its manifest check passes; keep the start-up refusal until then.
4. Put `config_key31` and `feasibility_fingerprint` into stored decisions so decisions are tied to 3.1 meanings.
5. Re-derive the synthetic evaluation for 3.1 (new scenarios, since D3 means something new), keep the 3.0 results as separate evidence, then evaluate against the same baselines.
6. Review the official procedures' source fidelity before drafting any 3.1 content for them.
