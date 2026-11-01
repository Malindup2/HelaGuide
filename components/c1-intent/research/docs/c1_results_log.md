## Observation 7: XLM-R results over 3 seeds (2026-10-16)
 
**Setup:** `c1_xlmr_train.ipynb`, xlm-roberta-base, 8 epochs, lr 3e-5, batch 16, max_len 128. Run 3 times with seeds 42, 1 and 2, each with its own 90/10 train/dev split by dialogue. Training data: synthetic silver set (650–658 train turns). Test data: gold set (142 turns, never used in training) and fresh set (50 turns, human-written, labelled from scratch).
Values are **mean ± standard deviation over the 3 seeds**.
Raw files: `results/xlmr_results_seed42.json`, `results/xlmr_results_seed1.json`, `results/xlmr_results_seed2.json`.
 
### Results
 
| Metric | Gold set | Fresh set |
|---|---|---|
| Language ID, SI/EN accuracy (XLM-R) | **0.991 ± 0.001** | **0.973 ± 0.005** |
| Language ID, all 5 tags | 0.991 ± 0.000 | 0.965 ± 0.007 |
| Language ID on Singlish (mixed / romanized) | 0.987 ± 0.001 | 0.955 ± 0.009 |
| Language ID at code-switch points | 0.990 ± 0.004 | 0.973 ± 0.007 |
| Language ID inside single-language runs | 0.991 ± 0.003 | 0.974 ± 0.004 |
| Intent accuracy, XLM-R (full history) | 0.933 ± 0.030 | 0.927 ± 0.023 |
| Intent macro-F1, XLM-R | 0.936 ± 0.025 | 0.926 ± 0.021 |
| Intent macro-F1, TF-IDF + LogReg baseline | **0.972** | **0.953 ± 0.014** |
| Entities, span micro-F1 (all types) | 0.528 ± 0.054 | 0.394 ± 0.080 |
| Entities, micro-F1 (types seen in training) | 0.584 ± 0.063 | – |
 
**Baselines on the fresh set (SI/EN words, deterministic, same every run):**
 
| | Heuristic word list | fastText lid.176 | XLM-R (mean) |
|---|---|---|---|
| All SI/EN words | 0.773 | 0.595 | **0.973** |
| Singlish (mixed / romanized) | 0.829 | 0.262 | **0.955** |
| Pure English | 0.495 | 0.808 | **0.990** |
| At code-switch points | 0.829 | 0.507 | **0.973** |
| Inside single-language runs | 0.738 | 0.651 | **0.974** |
 
### Takeaways
 
1. **Language ID is stable and strong.** It barely changes between seeds (± 0.001 on gold), so the result is reliable. It holds up on human-written text the model never saw (0.973).
2. **Switch points are no harder for XLM-R than the rest of the sentence** (0.973 vs 0.974 on fresh). fastText falls to 0.507 at switch points, about a coin flip. This is a key argument for token-level, context-aware segmentation over sentence-level tools.
3. **The MIXED tag cannot be measured yet.** There is only 1 MIXED word in each test set. Seed 2 missed it, which dropped its gold macro-F1 to 0.78 (vs 0.98 for the other seeds). Report per-tag scores for SI/EN/NE/OTHER, and state that MIXED is too rare to evaluate.
4. **TF-IDF beats XLM-R on intent** (0.972 vs 0.936 gold; 0.953 vs 0.926 fresh). Intents are signalled mainly by keywords (passport, NIC, nathi una / lost, renew). With ~650 training turns, a fine-tuned transformer gains nothing over keyword features. XLM-R also varies more between seeds (± 0.025). This is reported as a finding, not hidden. It also feeds sub-objective 3: model cost (cheap TF-IDF vs heavy XLM-R) becomes a second axis of the accuracy-vs-efficiency trade-off.
5. **One intent error is systematic.** In every seed, 2 gold `nic_new` turns are predicted as `birth_cert_copy`, most likely because the citizen mentions a birth certificate as a required document. The other errors change from seed to seed (e.g. seed 2: 3× `nic_update` → `nic_replace_lost`).
6. **Entities are the weakest part and unstable** (gold micro-F1 0.47–0.57; fresh 0.31–0.47).
   - District has high recall (0.96) but low precision (0.58), so it is over-predicted.
   - travel_date is also over-predicted.
   - `issue` and `service_mentioned` score 0, because they only occur in the support intents, which are missing from the synthetic training data.
   - **Planned fix:** a hybrid of a district gazetteer (all 25 districts, Sinhala script and romanized), a date/number pattern matcher and XLM-R for free-text slots, plus synthetic data for the support intents.
7. **Model storage:** the seed 42 models were saved to temporary Colab storage, not Drive, and are lost. The seed 1 and seed 2 models are on Drive (`MyDrive/c1_models/run_seed1`, `run_seed2`). **`run_seed1` is the deployment model** (best overall: gold intent 0.957, fresh language ID 0.979).
### Implications for the report
- Sub-objective 1 (token-level segmentation) is evaluated with multiple seeds, two baselines and a separate human-written test set.
- Sub-objective 2: intent is acceptable but not better than a simple baseline, and entities need the hybrid fix.
- Sub-objective 3: the next experiment compares context strategies (current turn only, sliding window, keyword summary, structured state, full history) by accuracy, tokens per turn and latency, for both XLM-R and TF-IDF.