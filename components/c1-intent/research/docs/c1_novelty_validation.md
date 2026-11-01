# HelaGuide C1: Validating the Novelty (SO3 Context Trade-off)

*Christine · J26-SE-354 · 21 Oct 2026 · branch `c1/context-v2`*

---

## 1. What we set out to prove

**Research gap (from the proposal):** code-switching NLP stops at single messages (Axis 1), dialogue state tracking is English-only and tied to fixed ontologies (Axis 2), and multi-turn efficiency work is language-agnostic and never tested on code-switched input (Axis 3). No study brings these together for Sinhala-English, or measures the accuracy-vs-efficiency trade-off.

**Research question:** how do context-management strategies affect intent/entity extraction accuracy against token cost and latency on Sinhala-English code-switched, multi-turn citizen-service dialogue?

### Hypotheses (one per gap axis)

| # | Hypothesis | Gap it tests |
|---|---|---|
| **H1** | Multi-turn context beats `current_only` on JGA | Axis 1: code-switching work stops at single messages |
| **H2** | Reduced context is not worse than `full_history`, at fewer tokens | **Core novelty:** the measured trade-off |
| **H3** | Context reduction hurts code-mixed turns differently from monolingual turns | Axis 3: efficiency never tested on code-switched input |
| **H4** | The hybrid tracker (rules + NER) degrades less than rules alone (fixed ontology) on messy input | Axis 2: fixed ontologies break on messy speech |
| **Scale** | Cheap and fast enough on CPU | "Run at national scale" in the gap |

---

## 2. Method

### Context strategies (7)
| Strategy | What the model reads |
|---|---|
| `current_only` | the current message only |
| `window_2` / `window_3` | the last 2 / 3 user messages |
| `keyword_summary` † | EN/NE words from earlier turns + the current message |
| `structured_state` † | previous intent + slots + the current message |
| `summary` (new) | earlier sentences with Sinhala/Singlish/English service or slot cues, capped at 48 XLM-R tokens |
| `full_history` | every user message so far |

† Oracle: reads gold tags at test time, so it's an upper bound.
LLM-based summary: future work (not run, to avoid API cost).

### Models and seeds
- **XLM-R** (`xlm-roberta-base`, fine-tuned, 15 epochs) and **TF-IDF + LogReg** (cheap baseline)
- **5 seeds** (1–5) → 70 prediction files, 391 test turns each

### Data
| Set | Turns | Role |
|---|---|---|
| gold | 142 | dev set for the tracker rules (reported separately) |
| synthetic | 199 | held out: 20% of the 977-turn silver set, split **by dialogue** (314 train / 79 test dialogues) |
| fresh | 50 | human-written, held out |
| **held-out (headline)** | **249** | synthetic + fresh |

Sessions are stitched from 2–4 dialogues **within each split only**. Dev = 10% of the train part, per seed. Tracker rules frozen (`c1_dst.py` at `8dd1f40`) before any context-v2 JGA was computed.

### Metrics
- **JGA** (joint goal accuracy, via the state tracker), intent accuracy, per-slot F1, span F1
- **Tokens per turn** (XLM-R tokenizer and tiktoken `cl100k_base`), latency
- **Code-Mixing Index (CMI)** per turn → buckets: pure SI (87), pure EN (33), low CMI (59), high CMI (50); median CMI of the mixed turns = 33.3

### Statistics
- Mean ± std **and median** over seeds
- **Cluster bootstrap** 95% CIs (resampling sessions, and seeds for H2)
- **H2:** non-inferiority CI at a 0.05 JGA margin (primary), McNemar + Holm (secondary), sensitivity at 0.03
- **H3:** **permutation test** within turn-position strata, 5000 permutations, Holm-corrected (chosen by calibration, see 3.3)
- **H4:** perturbation test, 4 types × 5 draws, fixed seed

---

## 3. Steps taken

### 3.1 Build (Claude Code, small reviewed commits)
| Stage | Work | Commit |
|---|---|---|
| 1 | Notebook rewrite: 7 strategies, per-turn predictions, synthetic split, `context_strategies.py` | `49f28c5` |
| 2 | `context_eval.py`: JGA via the tracker, CMI buckets, bootstrap, McNemar, interaction test, `summary.md` | `508f132` |
| 2b | H3 calibration and permutation test | `2ea300e` |
| — | Notes: run log and decisions (made **before** seeds 4–5) | `c123f29` |
| — | Convergence check, NI-primary H2, token ratio | `e009aba` |
| 3 | `perturb.py`: robustness test (H4) | `ddb6e2d` |
| 4 | `bench_cpu.py` + context tokens in `/details` and the demo | `14cfefe` (benchmark run, results in `4150efa`) |

### 3.2 Run
1. Colab (T4): seeds 1–3 → 42 files → preliminary analysis
2. Found **2 failed XLM-R runs** (window_2 s3, summary s3)
3. **Decided before seeing more data:** no post-hoc exclusion; add seeds 4–5; convergence rule as sensitivity only (recorded in notes, `c123f29`)
4. Colab: seeds 4–5 → 70 files total
5. Local: H3 calibration → robustness → `context_eval.py` into `results/context_v2_final/`

### 3.3 Safeguards (why the results can be trusted)
- **Clean split:** the synthetic test dialogues are never used for training or epoch selection (checked with asserts)
- **Paired design:** identical 391 turns in identical order across all 70 files
- **Calibrated H3 test:** on 200 null (no-effect) datasets:

  | Method | False "supported" rate (target ~5%) |
  |---|---|
  | **Permutation test (headline)** | **3.5–3.8%** |
  | Stratified bootstrap | 28.5–32.8% |
  | All turns, bootstrap | 55.5–70.0% |

- **Convergence check:** flags summary s3 and window_2 s3. **Excluding them changes no verdict.**
- **Oracle strategies** labelled as upper bounds everywhere
- **Invalid results marked:** hybrid NER on synthetic (the NER was trained on those dialogues)

---

## 4. Results (5 seeds, held-out JGA)

| Strategy | XLM-R | TF-IDF | XLM-R tokens/turn |
|---|---|---|---|
| current_only | 0.430 ± 0.012 | 0.392 ± 0.012 | 12.4 |
| window_2 | 0.561 ± 0.065 | 0.525 ± 0.014 | 22.1 |
| **window_3** | **0.624 ± 0.022** | **0.549 ± 0.006** | **30.1** |
| keyword_summary † | 0.537 ± 0.015 | 0.464 ± 0.018 | 23.2 |
| structured_state † | 0.602 ± 0.030 | 0.524 ± 0.012 | 32.0 |
| summary | 0.619 ± 0.027 | 0.455 ± 0.007 | 41.0 |
| full_history | 0.630 ± 0.021 | 0.440 ± 0.019 | 52.5 |

### Verdicts
| | XLM-R | TF-IDF |
|---|---|---|
| **H1** | ✅ **Supported:** every strategy beats current_only (+0.11 to +0.20 JGA, Holm p ≤ 0.0001) | Mixed |
| **H2** | ✅ **window_3 supported:** −0.006 JGA, CI [−0.043, +0.035], **43% fewer tokens** (not at the 0.03 margin) | ✅ Supported on fresh/held-out: less context is *better*; window_3 is **significantly better than full_history** (+0.108 JGA, CI [+0.048, +0.164], McNemar Holm p = 0.0001) |
| **H3** | ⚠️ Inconclusive (smallest Holm p = 0.09) | ⚠️ Inconclusive |
| **H4** | ⚠️ Inconclusive: hybrid drop 0.057 vs rules 0.041, diff −0.016 [−0.051, 0.000] (fresh) | — |
| **Scale** | ❌ **Not supported, on memory only:** deployed pipeline p95 152.8 ms (4 threads) is within the 500 ms budget, but memory is 3315 MB per worker vs the 2048 MB budget | TF-IDF: about 2 ms per turn at 1 thread |

---

## 5. Key findings

1. **Context matters for code-switched dialogue (H1).** Single-message models lose 0.11–0.20 JGA.
2. **The trade-off (core novelty, H2).** XLM-R with the last 3 messages stays within 5 JGA points of full history while reading 43% fewer tokens.
3. **The best context size depends on the model.** TF-IDF gets *worse* with more history (0.549 → 0.440); bag-of-words features get diluted. TF-IDF window_3 is significantly better than TF-IDF full_history (+0.108 JGA, CI [+0.048, +0.164], McNemar Holm p = 0.0001).
4. **No detectable code-mixing interaction (H3).** The savings from context reduction don't measurably hurt code-mixed turns more, at this sample size (~50 high-CMI turns). With 3 seeds, an uncalibrated test claimed an effect; the calibration and the extra seeds showed it was a false positive.
5. **Romanised spelling is the real weak spot (H4).** Rules JGA on synthetic drops 0.759 → 0.500 under spelling variants (aluth/alut, ikmanata/ikmanta). The NER fallback raises accuracy (+0.02 JGA) but isn't more robust.
6. **Token tax on Sinhala.** The LLM tokenizer (cl100k) uses 2.44× more tokens than XLM-R overall: **3.50× for pure Sinhala**, 0.95× for English, 2.14× for mixed.
7. **Fine-tuning instability.** 2 of 35 XLM-R runs failed to converge, but no verdict depends on them.

---

## Evidence map

Paths are relative to `components/c1-intent/research/`; results are in `results/context_v2_final/` unless noted.

| Claim | Test | Evidence file | Commit |
|---|---|---|---|
| Clean split: synthetic test dialogues never used for training or epoch selection | dialogue-level split, asserts in the notebook | `data/synthetic/context_v2_split.json`, `c1_context_experiment.ipynb` | `49f28c5` |
| Tracker rules and decisions fixed before seeds 4–5 | decision log, frozen `c1_dst.py` at `8dd1f40` | `docs/notes.md` (Obs 14–15), `docs/technicalWorkFlow.md` | `c123f29` |
| H1: every context strategy beats current_only (XLM-R) | exact McNemar + Holm; session cluster-bootstrap CI | `summary.md` (H1), `stats_tests.csv` | `508f132`, `4150efa` |
| H2: XLM-R window_3 not worse than full_history at 43% fewer tokens | non-inferiority CI (sessions + seeds), margin 0.05; McNemar secondary; sensitivity at 0.03 | `summary.md` (H2), `context_jga_results.json` (`h2_noninferiority`), `stats_tests.csv` | `e009aba`, `4150efa` |
| TF-IDF window_3 significantly better than full_history | NI CI [+0.048, +0.164]; McNemar Holm p = 0.0001 | `summary.md` (H2, TF-IDF) | `80831d2`, `4150efa` |
| H3 inconclusive; deployed window_3 interaction −0.97 points, CI [−9.15, +7.67] | permutation test within turn-position strata (Holm); cluster-bootstrap CI | `summary.md` (H3), `interaction_tests.csv` | `2ea300e`, `80831d2`, `4150efa` |
| H3 test is calibrated (false positives ≈ 5%) | 200 null data sets | `h3_calibration.csv`, `results/figures/h3_calibration.png` | `2ea300e`, `4150efa`, `c2ea009` |
| H4 inconclusive: hybrid not more robust than rules | 4 perturbations × 5 draws, cluster bootstrap over dialogues | `robustness.csv`, `robustness.png` | `ddb6e2d`, `4150efa` |
| Scale: latency within budget, memory misses it | CPU benchmark, batch size 1, 4 threads primary | `deployment_benchmark.csv/.json`, `summary.md` (scale), `results/figures/latency_vs_tokens.png`, `memory_vs_budget.png` | `14cfefe`, `69349fc`, `4150efa`, `c2ea009` |
| Token tax: 3.50× for pure Sinhala | cl100k / XLM-R token ratio per language bucket | `summary.md` (token tax), `results/figures/token_tax.png` | `e009aba`, `4150efa`, `c2ea009` |
| 2 XLM-R runs did not converge; excluding them changes no verdict | convergence rule (sensitivity only) | `convergence_check.csv`, `summary.md`, `results/figures/seed_spread.png` | `e009aba`, `4150efa`, `84152cd` |
| Language ID: XLM-R beats fastText and the heuristic (Obs 7) | word-level accuracy, fresh set, 3 seeds | `results/xlmr_results_seed{42,1,2}.json`, `results/figures/lid_comparison.png` | `c2ea009` (figure) |
| Slot memory gives the largest JGA gain (Obs 9) | tracker ablation, gold intent | `results/dst_results.json`, `results/figures/dst_ablation.png` | `c2ea009` (figure) |

---

## 6. Limitations

- Small held-out set (249 turns; fresh only 50), so H3/H4 have limited power
- Synthetic data is LLM-generated; fresh states are LLM-proposed and author-checked (no inter-annotator agreement yet)
- Short sessions (2–4 dialogues), so absolute token savings are small and the summary strategy rarely hits its cap
- Oracle strategies use gold tags
- Context reduction tested at the **application level**, not KV-cache (serving level)
- Sinhala-English only (Tamil and voice out of scope)
- The convergence rule was defined after seeing the failures (sensitivity only)

---

## 7. Still to do

- [x] **CPU benchmark** (`bench_cpu.py`) and re-run of `context_eval.py` for the scale claim: deployed pipeline p95 152.8 ms at 4 threads, within the 500 ms budget; memory 3315 MB misses the 2048 MB budget → scale **not supported, on memory only** (`4150efa`, `69349fc`). The 1-thread timings are unreliable on this Intel hybrid CPU; a high-priority rerun is still to do
- [x] McNemar "significantly better" label + H3 "rules out an interaction larger than X" sentence; for the deployed window_3 (single pre-specified comparison): interaction −0.97 JGA points, 95% CI [−9.15, +7.67] (`80831d2`)
- [x] Commit the results (small files only, `git add -f`; not `preds/` or `perturbed/`) (`4150efa`, per-seed JGA `84152cd`)
- [ ] Final observation in `notes.md` + H1–H4 results slide

### Future work
- Larger human-written test set + inter-annotator agreement (Cohen's kappa)
- Longer dialogues (6–10 turns) to show the growth in savings
- Singlish spelling normalisation / fuzzy matching before slot extraction
- LLM-based summary strategy
- Lighter pipeline: shared encoder with 3 heads, int8/ONNX, one intent call per turn
