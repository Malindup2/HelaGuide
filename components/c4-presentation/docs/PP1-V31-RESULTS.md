# PP1 v3.1 synthetic study: results

**SYNTHETIC EVALUATION ONLY.** Rewards come from an author-defined hypothetical model (`synthetic31.py`, `PP1-V31-SIMULATOR-FINDINGS.md`). Nothing here measures real-citizen comprehension, expert judgement or benefit. The 3.0 results (`PP1-SYNTHETIC-RESULTS.json`) are untouched.

Seeds: [11, 23, 37, 51, 71] (independent runs, never merged). Training observations per independent run: [0, 50, 200, 600, 2000, 5000] (checkpoints of one 5,000-observation run per seed and encoder). Development cases: 220; final test cases: 440 (including unseen procedures ['study-multiphase', 'study-mixed']). Feature schema `c4-features-pp1-1.1-525`; intervals are 95% Student-t over seeds.

## 1. Main result (balanced world, final test cases, 5,000 observations per run)

| Selector | Simulated expected reward |
|---|---|
| LinTS 525, exploration 1.0 (pre-declared) | 0.396 ± 0.006 |
| Standard guidance | 0.261 ± 0.000 |
| Minimal feasible support | 0.261 ± 0.000 |
| Maximal feasible support | 0.439 ± 0.000 |
| Best single configuration (hindsight) | 0.471 ± 0.000 |
| Random feasible | 0.328 ± 0.000 |
| Simulator oracle | 0.577 ± 0.000 |
| LinTS 525, exploration 0.25 (chosen on development cases) | 0.446 ± 0.010 |
| Diagnostic only: always the highest posterior mean (not LinTS) | 0.470 ± 0.011 |

Honest reading: LinTS clearly beats standard guidance (0.261) and random feasible (0.328). With exploration 0.25 it also edges the maximal-support baseline (0.446 versus 0.439, intervals nearly touching) but it does **not** beat the hindsight best constant configuration (0.471) and is far from the oracle (0.577). The posterior mean itself reaches the best-constant level (0.470): the policy has learned a good constant but has not yet shown context-specific gains beyond it, and Thompson sampling noise costs a further 0.02 to 0.07. Both effects shrink with more observations.

## 2. Learning curves (525, balanced world, test and development)

| Observations | Dev, exploration 1.0 | Test, exploration 1.0 | Dev, exploration 0.25 | Test, exploration 0.25 | Test, posterior mean (diagnostic) |
|---|---|---|---|---|---|
| 0 | 0.352 ± 0.007 | 0.350 ± 0.007 | 0.352 ± 0.007 | 0.350 ± 0.007 | 0.261 ± 0.000 |
| 50 | 0.348 ± 0.007 | 0.345 ± 0.004 | 0.331 ± 0.025 | 0.330 ± 0.026 | 0.359 ± 0.053 |
| 200 | 0.347 ± 0.008 | 0.345 ± 0.007 | 0.331 ± 0.006 | 0.328 ± 0.005 | 0.360 ± 0.044 |
| 600 | 0.357 ± 0.020 | 0.353 ± 0.013 | 0.366 ± 0.024 | 0.367 ± 0.024 | 0.408 ± 0.057 |
| 2000 | 0.367 ± 0.013 | 0.368 ± 0.012 | 0.398 ± 0.017 | 0.419 ± 0.022 | 0.443 ± 0.031 |
| 5000 | 0.383 ± 0.009 | 0.396 ± 0.006 | 0.416 ± 0.017 | 0.446 ± 0.010 | 0.470 ± 0.011 |

Baselines are identical at every checkpoint (same cases): test standard 0.261, maximal 0.439, best constant 0.471, random 0.328, oracle 0.577; development standard 0.267, maximal 0.424, best constant 0.460, random 0.330, oracle 0.566. Plots: `learning-curve-test.png`, `learning-curve-dev.png`.

## 3. Does a longer schedule help? (2 seeds trained to 15,000 observations, exploration 1.0)

| Seed | Obs | Dev | Test |
|---|---|---|---|
| 11 | 2000 | 0.349 | 0.354 |
| 11 | 5000 | 0.373 | 0.393 |
| 11 | 15000 | 0.391 | 0.431 |
| 23 | 2000 | 0.370 | 0.372 |
| 23 | 5000 | 0.388 | 0.394 |
| 23 | 15000 | 0.415 | 0.434 |

More observations kept helping (0.39 to 0.43 on test between 5,000 and 15,000) without saturating; the exploration-0.25 setting reaches at 5,000 about what exploration 1.0 reaches at 15,000. More data does not guarantee a better policy, but here it did, slowly.

## 4. Development-only exploration sweep (525, 3 seeds, 5,000 observations)

| Exploration scale | Dev reward |
|---|---|
| 0.1 | 0.393 ± 0.018 |
| 0.25 | 0.415 ± 0.047 |
| 0.5 | 0.403 ± 0.024 |
| 1.0 (pre-declared) | 0.383 ± 0.009 (5 seeds) |

0.25 was best on development cases, so it was adopted as a second, clearly labelled configuration; its final-test numbers were computed afterwards and were not used for the choice. The same seeds reproduced identical numbers in two separate output folders.

## 5. Encoder ablations (balanced world, test, 5,000 observations, exploration 1.0)

| Encoder | LinTS reward |
|---|---|
| 416 features | 0.382 ± 0.014 |
| 451 features | 0.393 ± 0.008 |
| 516 features | 0.392 ± 0.004 |
| 525 features | 0.396 ± 0.006 |

The larger encoders learn faster; at 5,000 observations 451, 516 and 525 are within about 0.014 of each other and 416 is lower. No encoder was selected on test reward.

## 6. Sensitivity to the simulator assumption (525 trained under `balanced`, 5,000 observations, test)

| World | LinTS | Standard | Maximal | Best constant | Random | Oracle |
|---|---|---|---|---|---|---|
| balanced | 0.396 ± 0.006 | 0.261 | 0.439 | 0.471 | 0.328 | 0.577 |
| under heavy | 0.318 ± 0.009 | 0.188 | 0.471 | 0.486 | 0.256 | 0.537 |
| over heavy | 0.458 ± 0.007 | 0.407 | 0.401 | 0.443 | 0.403 | 0.623 |
| preference led | 0.588 ± 0.005 | 0.470 | 0.584 | 0.612 | 0.544 | 0.700 |
| low need | 0.413 ± 0.015 | 0.650 | 0.230 | 0.276 | 0.397 | 0.696 |
| flat | 0.600 ± 0.000 | 0.600 | 0.600 | 0.600 | 0.600 | 0.600 |

Standard guidance is the best simple option only in the `low_need` world (0.650 versus LinTS 0.413) and ties everything in the `flat` world. The conclusion "personalisation beats standard" therefore depends on the assumption that many citizens need support; it is reversed when most need little.

## 7. Matched-assumption runs (525, 3 seeds, 2,000 observations, trained and evaluated under the same world, test)

| World | LinTS at 0 | LinTS at 2,000 | Standard | Best constant | Oracle |
|---|---|---|---|---|---|
| low need | 0.355 ± 0.024 | 0.510 ± 0.015 | 0.650 | 0.276 | 0.696 |
| under heavy | 0.292 ± 0.003 | 0.334 ± 0.014 | 0.188 | 0.486 | 0.537 |
| over heavy | 0.404 ± 0.025 | 0.435 ± 0.016 | 0.407 | 0.443 | 0.623 |
| preference led | 0.558 ± 0.021 | 0.567 ± 0.012 | 0.470 | 0.612 | 0.700 |

In the `low_need` world the learner improves (0.36 to 0.51) toward but does not reach standard guidance (0.65) within 2,000 observations, so learning to give LESS support is slower than learning to give more. In the other worlds it improves but does not beat the best constant.

## 8. Scenario families (525, exploration 1.0, test, 5 seeds, 5,000 observations)

| Family | Hypothesis | LinTS | Standard | Oracle | Mean support given | Mean support of the best choice |
|---|---|---|---|---|---|---|
| N1 | Familiar citizen, simple procedure, wants to scan requirements quickly | 0.501 | 0.736 | 0.739 | 1.74 | 0.15 |
| N2 | Unfamiliar citizen, simple procedure, wants short but clear instructions | 0.357 | 0.198 | 0.462 | 2.28 | 2.85 |
| N3 | Unfamiliar citizen, information-heavy procedure, may benefit from richer explanation | 0.303 | 0.084 | 0.415 | 2.14 | 2.90 |
| N4 | Low-confidence citizen who dislikes long explanations | 0.386 | 0.173 | 0.585 | 2.94 | 4.20 |
| N5 | Experienced citizen facing a new, complex procedure | 0.369 | 0.083 | 0.639 | 3.54 | 4.45 |
| N6 | Citizen who prefers Overview despite limited familiarity | 0.370 | 0.149 | 0.621 | 3.30 | 4.40 |
| N7 | Branch-heavy procedure where route alternatives matter | 0.414 | 0.212 | 0.579 | 3.01 | 3.95 |
| N8 | Dependency-heavy procedure where Inline or Map support may help | 0.348 | 0.093 | 0.596 | 3.57 | 4.85 |
| N9 | Genuine parallel tasks where relationship representation matters | 0.360 | 0.131 | 0.620 | 3.53 | 4.65 |
| N10 | Multiphase procedure where Segmentation and possibly Recap may help | 0.373 | 0.128 | 0.629 | 3.59 | 4.70 |
| N11 | Procedure where added scaffolding provides no benefit | 0.600 | 0.600 | 0.600 | 2.51 | 0.00 |
| N12 | Preferences that conflict with context or hard accessibility requirements | 0.350 | 0.301 | 0.454 | 1.45 | 2.15 |
| S1 | Familiar citizen, simple procedure | 0.478 | 0.708 | 0.711 | 1.80 | 0.15 |
| S2 | Unfamiliar citizen, same simple procedure | 0.350 | 0.174 | 0.448 | 2.13 | 2.85 |
| S3 | Unfamiliar citizen, information-heavy procedure | 0.312 | 0.080 | 0.496 | 2.49 | 3.75 |
| S4 | Procedural relationships | 0.352 | 0.159 | 0.590 | 3.17 | 4.50 |
| S5 | Multi-phase orientation | 0.281 | 0.050 | 0.602 | 3.57 | 5.65 |
| S6 | Conflicting preferences and accessibility | 0.375 | 0.283 | 0.546 | 2.34 | 2.90 |
| S7 | Familiar citizen, complex procedure (counterexample) | 0.387 | 0.299 | 0.596 | 3.11 | 3.05 |
| S8 | Unfamiliar citizen, simple procedure (counterexample) | 0.422 | 0.206 | 0.541 | 2.87 | 3.50 |
| S9 | Null support effect | 0.600 | 0.600 | 0.600 | 2.54 | 0.00 |
| S10 | High support burden sensitivity | 0.416 | 0.290 | 0.624 | 2.76 | 3.55 |

Compact cases (S1, N1: familiar citizens on short procedures) are where standard guidance equals the oracle and LinTS gives too much support (about 1.8 scaffolds against 0.15 best): over-support. Rich cases (S5, N8 to N10) are where the best choice gives 4 to 5.7 scaffolds and LinTS gives about 3.5: under-support. Null cases (S9, N11) correctly tie at 0.600.

Unseen procedures (never in training): LinTS 0.349, standard 0.134, best constant 0.540, oracle 0.594. Seen procedures with new contexts: LinTS 0.408, standard 0.293, best constant 0.454.

Mean mismatch of the selected support (test, 525, 5,000 observations, balanced world): under-support 1.782 ± 0.061, over-support 0.698 ± 0.038. Constraint violations in every evaluation: 0.

## 9. Replay and determinism

Exact selected-only replay (every sampled-score vector, selected feature vector, revision, update chain and checkpoint recomputed from the immutable trace) passed for `seed-11-525`, `seed-23-x0.25-525`, `seed-51-416` and `seed-71-516`, 5,000 observations each. Re-assessing all 22 result files from the saved checkpoints reproduced every original sampled-selection number exactly before adding the greedy diagnostic. Evaluation never changed a posterior (asserted on every assessment).

## 10. Limitations

- SYNTHETIC EVALUATION ONLY: the response model is author-defined, external expert review is pending, and nothing here measures real-citizen comprehension or benefit.
- The primary 'balanced' world contains many high-need citizens, so standard guidance does poorly in it by construction; 'low_need' is the opposite world. Conclusions must be read across assumptions.
- Study procedures are fictional with templated wording; official procedures are fallback probes with only four feasible configurations each.
- Binary rewards under a Gaussian linear surrogate are misspecified; sampled scores are not calibrated probabilities.
- Encoder variants and budgets are compared on development cases; the final test cases were not used for any choice.
- The study procedures are fictional with templated wording; the final-test unseen procedures were generated by the same author who wrote the simulator, so structural generalisation is optimistic.
- The learner is evaluated with Thompson sampling, which deliberately explores; its numbers include that exploration cost.
