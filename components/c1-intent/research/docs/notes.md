# Research Notes — Sinhala-English Code-Switched Intent & Entity Engine

## Environment (set up 2026-10-02)
- Project folder: `D:\Research\cs-intent-engine` (data/, models/, notebooks/, src/)
- Conda env `nlp`, Python 3.10
- torch 2.14.1+cpu, transformers 5.18.0
- fastText model: `models/lid.176.bin`
- Training will run on Google Colab (GPU); local machine for data, labelling, baselines

### Setup issues and fixes
- `conda create` failed: Anaconda channel Terms of Service not accepted → ran `conda tos accept` for each channel
- torch DLL blocked by Windows Application Control (WinError 4551) → resolved
- fastText `predict()` crashes with NumPy 2 (`copy=False` error) → `pip install "numpy<2"`
- Hugging Face symlink warning on Windows: harmless, only uses more disk space

---

## Observation 1: fastText baseline on code-switched input (2026-10-02)

| Input | Script | fastText prediction | Confidence |
|---|---|---|---|
| `mata NIC eka ganna one` | Romanized (Singlish) | `en` | 0.208 |
| `මට NIC එක ගන්න ඕනේ` | Sinhala script | `si` | 0.996 |

**Takeaways**
- Sinhala in native script is identified almost perfectly.
- Romanized Sinhala (Singlish) is misidentified as English, with low confidence (~21%). The sentence is mostly Sinhala.
- fastText gives one label per sentence, so it cannot do token-level segmentation (e.g. `mata`=SI, `NIC`=EN, `eka`=SI).
- **Implication:** off-the-shelf language ID fails on the most common way citizens type. This motivates a fine-tuned token-level segmentation layer (XLM-RoBERTa), and confirms romanized Sinhala must be in the dataset, not only Sinhala script.

---

## Observation 2: XLM-RoBERTa tokenization of Singlish (2026-10-02)

Input: `mata NIC eka ganna one` (5 words)

Output: `['▁mata', '▁', 'NIC', '▁e', 'ka', '▁gan', 'na', '▁one']` (8 subword tokens)

**Takeaways**
- Romanized Sinhala words are fragmented (`eka` → `e` + `ka`, `ganna` → `gan` + `na`), suggesting limited exposure to Singlish in pretraining.
- Singlish costs more tokens per word than English, which directly affects the token-usage measurements in the efficiency trade-off study.
- **Methodology decision:** token counts must use the tokenizer of the model actually processing the context, not word counts or tiktoken.
- **Labelling decision:** labels are assigned per word; during training, each word's label maps to its first subword, and continuation pieces are ignored in the loss (standard token-classification alignment).

---

## Observation 4: Synthetic data and tag quality (2026-10-15)
- 233 synthetic dialogues (Claude Code 145+40, Gemini 3.5 Flash Lite 48 minus 2 removed for
  leaked field names / merged tokens); ~30 per core intent.
- Generator acceptance: Claude Code 92–100% (rejections only duplicates); Gemini Lite 78%
  (invalid JSON, out-of-schema slots, duplicates).
- Word-level language tags by Claude Code; 80 turns (418 tokens) hand-reviewed:
  LLM tags 100% agreement; heuristic 88.7% on mixed, 100% on pure Sinhala.
- Heuristic accuracy on gold (98.5%) is inflated by pre-label anchoring; 88.7% is the fairer estimate.
- Training file: `data/synthetic/silver_tokens.jsonl` (618 turns). Test set stays `data/gold_tokens.jsonl`.

---

## Observation 5: First XLM-R results (2026-10-15)
xlm-roberta-base, 8 epochs, seed 42; trained on 555 synthetic turns, tested on 142 gold turns.
- Language ID: SI/EN accuracy 0.987 (Singlish 0.983 vs fastText 0.352); all-tags 0.986.
  Heuristic scores ~0.985 on gold but that is inflated by pre-label anchoring (0.887 on fresh data).
- Entities: micro-F1 0.63 on learnable types. district R 0.97 / P 0.60 (over-predicts places);
  travel_date P 0.38. issue/service_mentioned not in training data.
- Intent (full history, 8 core intents, n=70): acc 0.957, macro-F1 0.956. 2 of 3 errors are
  intent switches (birth cert -> NIC): earlier context misleads full-history input.
- Limitations: single run/seed; small gold set; gold intents outside the 8 core (72 turns) not yet covered.

---

## Observation 6: Fresh human-written test set (2026-10-16)
23 dialogues / 50 turns / 403 words written and labelled from scratch by the author
(no pre-labels; LLM key used as second annotator — **TODO: state how it was used**).
XLM-R trained on 726 synthetic turns (5 styles), 1 seed.

| SI/EN accuracy | Heuristic | fastText | XLM-R |
|---|---|---|---|
| All (n=375) | 0.773 | 0.595 | 0.971 |
| Singlish | 0.829 | 0.262 | 0.945 |
| Pure English | 0.495 | 0.808 | 0.990 |
| Sinhala script + EN | 0.913 | 0.888 | 0.988 |
| Pure Sinhala | 1.000 | 0.906 | 1.000 |

- Gold set: XLM-R SI/EN 0.990. Heuristic's 0.985 on gold was inflated (0.773 here).
- Intent: fresh 0.90 (n=50), gold 0.943 (n=70); intent-switch errors persist with full history.
- Entities: micro-F1 fresh 0.47 (n=14), gold 0.63 — over-prediction of district/travel_date.
- Limitations: single seed, small fresh set (~±2 pts), 4 gold intents not yet covered.

---

## Next steps (early October list, all done; current tasks are in `TASKS.md`)
- [x] Install Label Studio (env `label`)
- [x] Define intent list and slots per intent (align with Knowledge Graph ontology)
- [x] Write 50–100 seed dialogues (Sinhala script + Singlish, 1–5 turns, with corrections)
- [x] Label seed data: token language tags, entities, intent
- [x] Run fastText baseline on full seed set and log the result




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



## Observation 8: context strategies, accuracy vs efficiency (2026-10-16, FINAL)
 
**Setup:** `c1_context_experiment.ipynb`, 6 context strategies × 3 seeds (1, 2, 42). For each strategy, XLM-R (xlm-roberta-base, 15 epochs, best epoch chosen on the synthetic dev set) and TF-IDF + LogReg are trained on the same inputs.
- **Training data:** synthetic dialogues joined into sessions of 2–4 dialogues.
- **Test data:** gold and fresh sets, both as their original dialogues and as joined sessions (a fixed join, the same for every run).
- **Truncation** is from the left (oldest text dropped first). Inputs over 128 tokens: 0%, except full history on fresh sessions (2%).
- **Tokens** are counted with the XLM-R tokenizer.
- **Latency** is per turn at batch size 1.
Values are macro-F1, mean ± std over 3 seeds. Raw files: `results/c1_context_results_e15.json` (final) and `results/c1_context_results_e6.json` (first run, under-trained).
 
### Gold sessions (70 core turns: 25 intent-switch turns, 38 same-intent follow-ups)
 
| Strategy | Tokens/turn | XLM-R | TF-IDF |
|---|---|---|---|
| current_only | 11.5 | 0.589 ± 0.005 | 0.634 ± 0.016 |
| window_2 | 20.5 | **0.895 ± 0.016** | **0.892 ± 0.021** |
| window_3 | 27.5 | **0.896 ± 0.017** | 0.881 ± 0.022 |
| keyword_summary | 21.2 | 0.705 ± 0.014 | 0.652 ± 0.043 |
| structured_state | 25.5 | 0.878 ± 0.046 | 0.790 ± 0.079 |
| full_history | 42.5 | **0.897 ± 0.045** | 0.683 ± 0.082 |
 
### Fresh sessions (human-written; 50 core turns, 16 intent switches)
 
| Strategy | Tokens/turn | XLM-R | TF-IDF |
|---|---|---|---|
| current_only | 14.6 | 0.656 ± 0.090 | 0.621 ± 0.010 |
| window_2 | 26.0 | 0.833 ± 0.043 | 0.837 ± 0.001 |
| window_3 | 35.2 | 0.898 ± 0.029 | 0.819 ± 0.021 |
| keyword_summary | 26.2 | 0.841 ± 0.044 | 0.775 ± 0.033 |
| structured_state | 24.7 | 0.835 ± 0.064 | **0.895 ± 0.044** |
| full_history | 55.3 | **0.935 ± 0.022** | 0.634 ± 0.043 |
 
**Original short dialogues** (2–3 turns, for reference), XLM-R / TF-IDF:
- gold: full history 0.941 / 0.951, structured state 0.940 / 0.966
- fresh: full history 0.929 / 0.930, window_3 0.909 / 0.923
### Accuracy by turn type (gold sessions)
 
| Strategy | XLM-R, switch turns | XLM-R, same-intent follow-ups | TF-IDF, switch turns |
|---|---|---|---|
| current_only | 0.880 | **0.395** | 0.947 |
| window_2 | 0.840 | 0.903 | 0.893 |
| full_history | 0.853 | 0.903 | **0.613** |
 
### Latency per turn
 
| | current_only | window_2 | window_3 | full_history |
|---|---|---|---|---|
| XLM-R, T4 GPU | 9.6 ms | 9.8 ms | 10.4 ms | 10.2 ms |
| XLM-R, CPU | 106 ms | 123 ms | 133 ms | **155 ms** |
| TF-IDF, CPU | 2.0 ms | 2.3 ms | 2.3 ms | 2.4 ms |
 
### Takeaways
 
1. **Context is needed for follow-up turns, not for switch turns.**
   - With the current message only, XLM-R gets just 0.395 on same-intent follow-ups ("Matara", "ow urgent"). Any context strategy brings that to about 0.90.
   - Switch turns name the new service in the message itself, so the current message alone scores well (0.88).
2. **The best context strategy depends on the model.** This is the central result.
   - **TF-IDF gets worse with more context.** In sessions, full history drops to 0.683 (gold) and 0.634 (fresh). At switch turns it falls to 0.613, because keywords from the previous topic outvote the new one. Its best options are short and compact: window_2 (gold 0.892) and structured state (fresh 0.895).
   - **XLM-R is robust to stale context.** Full history is the best or tied-best strategy for it.
3. **For XLM-R, a short window gives most of the accuracy for much less input.**
   - **Gold:** window_2 equals full history (0.895 vs 0.897) with **52% fewer tokens** (20.5 vs 42.5) and lower variance across seeds (± 0.016 vs ± 0.045).
   - **Fresh:** full history is best (0.935). window_3 gives 0.898 (−0.037) with 36% fewer tokens.
   - **The accuracy-vs-cost trade-off is real:** full history buys a small gain on human-written text at a token cost that keeps growing with the conversation.
4. **Full-history cost grows with every turn; window costs stay flat.** Full history reaches about 70 tokens by turn 6, while windows stay at 20–35. On CPU, full history is 46% slower than current_only and 26% slower than window_2. GPU latency is flat at these lengths. For longer real conversations, full history would hit the 128-token limit, and left truncation would turn it into a window anyway.
5. **The keyword summary is the weakest context strategy for both models.** XLM-R scores 0.705 on gold sessions. It keeps only English words and names, but in Singlish the words that separate one service from another are often Sinhala (*nathi una* = lost, *aluth* = new). **Code-switching finding:** context compression that keeps only the English part of the text loses the intent signal.
6. **Cheap vs heavy model.**
   - On fresh sessions, TF-IDF + structured state (0.895, 24.7 tokens, about 2 ms on CPU) matches XLM-R + window_3 (0.898, 35.2 tokens, 133 ms on CPU).
   - On gold sessions, TF-IDF + window_2 (0.892) matches XLM-R + full history (0.897, 155 ms on CPU).
   - With a well-chosen context strategy, a model about 50–70× cheaper (at batch size 1 on CPU) gets within about 0.04 F1 of the best result.
7. **Training length mattered.** In run 1, with 6 epochs, XLM-R was under-trained. Structured state scored 0.700 ± 0.168, which rose to 0.878 ± 0.046 at 15 epochs. Run 1 had also suggested that window_3 beats full history; with proper training they tie. Conclusions are drawn from the 15-epoch run.
8. **Remaining errors:** the systematic `nic_new` → `birth_cert_copy` confusion (d051, d069) persists under full history. In structured state, the errors are mostly between NIC variants: `nic_new` / `nic_update` / `nic_replace_lost`.
### Recommendation for the C1 engine
- **Default:** XLM-R + window_3. It is within 0.001 of full history on gold and 0.037 on fresh, has a fixed input size (cost does not grow with the conversation) and is stable across seeds.
- **Low-resource / CPU option:** TF-IDF + structured state or window_2, at about 2 ms per turn.
- **Never** pair TF-IDF with full history.
### Caveats
- The test sets are small: 70 gold and 50 fresh core turns.
- Sessions are artificial joins of 2–3-turn dialogues. Real long conversations (5+ turns) are still needed.
- keyword_summary and structured_state read the gold language/entity tags (an oracle). With predicted tags, structured state would be somewhat lower.
- Only intent is measured; slot tracking (joint goal accuracy) is not yet included.
 
## Observation 9: multi-turn slot tracking and joint goal accuracy (2026-10-18)
 
**Setup:** `experiments/c1_dst.py` (hybrid slot extractor + dialogue state tracker) and `experiments/dst_eval.py`. No training needed; it runs on CPU in seconds. Raw file: `results/dst_results.json`.
 
- **Hybrid extractor:**
  - district gazetteer: 25 districts in English, romanized and Sinhala-script spellings
  - date pattern matcher (English and Sinhala months, relative dates) → canonical form
  - keyword rules for fixed-choice slots (applicant_for, change_field, urgency, service_type)
  - service, purpose and complaint-type lists
  - the bot's last question, so the answer "Matara" to "Koheda?" fills `district`
- **Tracker:**
  - carries slots across turns
  - in-turn corrections ("Kandy... sorry, Matale", "18, 8 nemei")
  - yes/no answers and confirmations ("District eka Colombo neda?" → "ow")
  - after an intent switch, keeps only the slots the new intent uses
- **Metric:** joint goal accuracy (JGA), meaning the intent **and** every slot value are correct at that turn, plus per-slot F1. Free-text values are matched leniently (one contains the other); dates are compared as canonical token sets.
**Important for honesty:**
- The rules were written while reading the **gold** dialogues, so gold is a *development* set and its JGA is optimistic.
- Two sets were never used to write the rules:
  - the **synthetic** dialogues (726 turns)
  - the **fresh** dialogues (50 turns, human-written; states proposed by an LLM and checked by the author)
  These two are the real test.
### JGA by tracker setting (intent = gold label, so this isolates slot tracking)
 
| Tracker setting | Gold (dev, 142 turns) | Synthetic (held-out, 726) | Fresh (held-out, 50) |
|---|---|---|---|
| 1. No memory (current message only) | 0.528 | 0.477 | 0.720 |
| 2. + carry slots across turns | 0.838 | 0.718 | 0.860 |
| 3. + the bot's question (answers, yes/no, confirmations) | 0.901 | 0.762 | 0.880 |
| 4. + corrections, switch handling, negation (**full**) | 0.979 | **0.807** | **0.920** |
 
On turns after the first, the full tracker scores 0.889 on fresh and 0.746 on synthetic, against 0.519 and 0.236 with no memory.
 
### With predicted intent (TF-IDF, last 3 messages, trained on silver)
 
| | Intent accuracy | JGA |
|---|---|---|
| Fresh (8 core intents) | 0.96 | **0.88** |
| Gold, core-intent dialogues | — | 0.924 |
| Gold, all turns | 0.47 | 0.458 |
 
On gold, all turns score low because more than half the gold turns (72 of 142) are support intents, which have no training data yet.
 
### Entity spans: hybrid vs XLM-R NER
 
Same span-level metric as Observation 7. "Extractive types" are district, dates and new_value, the slots whose value is a piece of the user's text.
 
| | Gold | Fresh |
|---|---|---|
| XLM-R NER (3-seed mean, Obs. 7) | 0.655 | 0.481 |
| Hybrid extractor | **0.750** (P 1.00, R 0.60) | **0.727** |
 
- The hybrid never adds a wrong span on gold (precision 1.0).
- Most of its missed gold spans are districts typed in `unsupported_service` dialogues. The intent schema doesn't track district there, so the tracker deliberately ignores them.
### Per-slot F1 (full tracker, held-out sets)
 
| Slot | Synthetic F1 (n) | Fresh F1 (n) |
|---|---|---|
| district | 0.971 (333) | 1.000 (4) |
| urgency | 0.958 (37) | — |
| purpose | 0.944 (127) | 1.000 (4) |
| change_field | 0.934 (95) | 1.000 (6) |
| applicant_for | 0.924 (256) | 0.923 (13) |
| service_type | 0.890 (80) | 1.000 (1) |
| date | 0.878 (73) | 1.000 (4) |
| travel_date | 0.868 (101) | 1.000 (1) |
| date_of_birth | 0.600 (49) | — |
| new_value | 0.561 (40) | 0.500 (2) |
 
### Takeaways
1. **Remembering across turns is the biggest gain.** Carrying slots raises JGA by about 0.14–0.24, and using the bot's question adds a little more. On follow-up turns, memory takes fresh JGA from 0.52 to 0.89.
2. **The tracker generalises.** On the two sets it was not built from, full JGA is 0.81 (synthetic) and 0.92 (fresh), against 0.98 on the development set. Report the held-out numbers.
3. **The hybrid extractor beats XLM-R NER** on the extractive slots (fresh 0.73 vs 0.48) and needs no training data. It also fixes the over-prediction problem from Observation 7 (gold precision 1.00).
4. **The full pipeline works on human-written text.** With *predicted* intent, fresh JGA is 0.88.
5. **Remaining errors** (found on the held-out sets; to fix after PP1 and re-test on new data):
   - dates in other formats (`2010.04.18`, `labana avurudde january 15`, "last week" read as a date of birth)
   - new values given in the first message without a bot question (`new_value` 0.56)
   - corrections that give only the new number ("ne ne sry 54/2")
   - a later mention of another person overwriting `applicant_for` ("thaththa abroad")
6. **Support intents** still have no training data. That limits the predicted-intent JGA on gold, and is the next data task.
### Caveats
- The fresh states were LLM-proposed and author-checked, not labelled independently.
- Fresh is small (50 turns, few examples per slot).
- The issue categories (fee, documents, office hours, photo) are a small hand-made list.
- The XLM-R NER + rules combination is reported in Observation 10 (fresh entity F1 0.783, fresh JGA 0.94).


## Observation 10: retrained with all 12 intents (v2), and the full pipeline (2026-10-18)
 
**Setup:**
- `c1_xlmr_train_v2.ipynb`, seed 1, xlm-roberta-base fine-tuned for 8 epochs.
- Intent reads the **last 3 user messages**, cut from the left.
- New silver set: 393 dialogues / 977 turns, now including 120 dialogues for the 4 support intents.
- Models: `MyDrive/c1_models/run_v2_seed1`. Results: `results/xlmr_results_v2_seed1.json` and `results/dst_results.json`.
- Single seed, so treat differences under about 0.03 as noise.
### Intent (now scored on all 142 gold turns, not 70)
 
| | Gold accuracy | Gold macro-F1 | Fresh accuracy (core intents only) |
|---|---|---|---|
| XLM-R v2 (12 intents, window_3) | **0.852** | **0.791** | 0.88 |
| TF-IDF + LogReg (same input) | 0.782 | 0.772 | 0.92 |
| *Before (v1, 8 intents, 70 gold turns): XLM-R* | *0.933* | *0.936* | *0.927* |
 
- **With 12 intents, XLM-R now beats TF-IDF on gold.** The support intents are harder to spot by keywords, so a contextual model helps. This reverses Observation 7, where only the 8 keyword-heavy core intents were scored.
- **Per intent:**
  - unsupported_service: F1 0.90 (54 turns)
  - feedback_complaint: F1 0.80 (recall 0.67)
  - out_of_scope: F1 0.75
  - **general_question: F1 0.00** (5 turns), the weakest class; these are confused with nic_update, passport_new and unsupported_service
- **Most common gold error:** 5× unsupported_service → passport_renew. The word "renew" appears in licence renewals too.
- **Fresh accuracy fell slightly** (0.927 → 0.88): with 12 classes there are more ways to be wrong, e.g. 2 marriage turns → unsupported_service.
- **XLM-R intent is under-trained.** Training loss was still 0.41 at epoch 8 (0.04 in v1), and dev macro-F1 peaked at 0.69. A 15-epoch run is the obvious next step, as in Observation 8.
### Language ID (unchanged, stable)
- Gold SI/EN: 0.989. Fresh: 0.971.
- At switch points: 0.993 gold / 0.973 fresh.
### Dialogue state tracking (JGA)
 
| Setting | Gold (dev) | Fresh (held-out) |
|---|---|---|
| Rules tracker, gold intent | 0.979 | 0.92 |
| Rules tracker + XLM-R NER fallback, gold intent | 0.979 | **0.94** |
| Full pipeline, **TF-IDF** intent | 0.796 | 0.84 (0.86 with NER) |
| Full pipeline, **XLM-R** intent | **0.838** | 0.82 (0.84 with NER) |
| XLM-R NER alone (no rules), gold intent | 0.254 | 0.48 |
 
- On gold, all turns, the full pipeline rises from 0.46 (before the support-intent data) to **0.84**.
- **The rules carry slot tracking.** XLM-R NER on its own reaches only 0.25–0.48 JGA. Used as a **fallback** for free-text slots the rules miss, it adds a little: fresh 0.92 → 0.94, one turn.
- **Synthetic held-out set:** the rules tracker alone scores 0.746 (977 turns, now including support dialogues). With the NER fallback it shows 0.851, but **that number is not valid**: the NER model was trained on 90% of these dialogues. Use the fresh set for the NER comparison.
### Entity spans, extractive types (fresh, held-out)
 
| XLM-R NER v2 | Hybrid rules | Hybrid + XLM-R NER |
|---|---|---|
| 0.455 | 0.727 | **0.783** |
 
### Takeaways
1. **All 12 intents are now recognised and scored.** The pipeline handles complaints (routed to trust verification), unsupported services and off-topic messages. Gold JGA rose from 0.46 to 0.84.
2. **The model choice flips with the task.** For the 8 keyword-heavy service intents, TF-IDF was as good or better. With the support intents, XLM-R is better on gold (0.852 vs 0.782). TF-IDF stays a strong low-cost option and is slightly better on the fresh core-intent set.
3. **Hybrid design confirmed.** Rules for slot tracking, plus XLM-R NER only as a fallback for free text, gives the best entity F1 (0.78) and fresh JGA (0.94).
4. **Weak spots to fix next:**
   - general_question (needs more varied examples)
   - "renew" in licence questions read as passport_renew
   - XLM-R intent under-training (rerun at 15 epochs, 3 seeds)
### Deployment choice
`run_v2_seed1` (12 intents, window_3, left truncation) + the rules tracker + the XLM-R NER fallback. This replaces `run_seed1`.


## Observation 11: keeping the topic across turns, and always replying (2026-10-19)

**Problem.** The intent model labels every message again, so short follow-up answers can change the topic.
- Replaying the conversation "passport ekak mata ganna puluwnda" → "normal" → "next year, mata wayasa 14i" → "next year" → "ganna puluwnda" → "galle" on `run_v2_seed1`:
  - "ganna puluwnda" comes out as `nic_new` at 0.39
  - "next year" comes out as `passport_new` at 0.34
- The service threshold is 0.35, so before this change the 0.39 turn would have replaced the passport request with `nic_new`.
- Bot questions were also only templates in the demo page; the engine itself did not reply.

**Change (no retraining).** A policy in `Session` (`experiments/c1_engine.py`, copied to the service):
- **Active intent.**
  - A core intent becomes the conversation's `active_intent` at confidence ≥ 0.6, or ≥ 0.5 on the first turn.
  - Later turns keep it. They switch only when a different core intent is predicted at ≥ 0.75 **and** the message names that service. The keyword lists are `SERVICE_KEYWORDS` in `c1_dst.py`, next to `KG_SERVICE_IDS`.
  - When the bot's last question asked for a slot that is still missing, the answer never switches.
  - Low-confidence turns still fill the active intent's slots.
- **Complaints.** `feedback_complaint` is still routed to trust verification, but it does not replace the active intent. The next turn resumes it.
- **Slots per intent.**
  - Each intent keeps its own slot state.
  - On a switch, district and applicant_for carry over, also when they were said under an intent that has no such slot (a district mentioned during a passport request).
  - Switching back restores the old intent's slots.
- **A reply on every turn**, in the script the user typed (Sinhala script, English or Singlish):
  - the question for the next missing slot
  - a confirmation when all slots are filled (`ready`)
  - "which service?" on an unsure first turn
  - fixed replies for unsupported, off-topic and unclear messages
- Slot questions are worded so the tracker recognises them when they come back as the bot's last question.

**Replay on `run_v2_seed1`** (live service, each reply sent back as the bot's last question):
- The passport conversation above stays `passport_new` on all 6 turns. `service_type` stays `normal`, and it ends with "Hari — normal new passport, oyata, travel next year. Documents tika pennannam."
- A real switch works. After a completed passport request, "NIC ekath aluthen ganna one" (`nic_new` 0.77, names NIC) switches. Galle, said in the first passport message, and `applicant_for` carry over.
- Demo sessions A, C, Sinhala script and English give the same intents as before (A and Sinhala script also the same slots), now with replies.
- The first version picked the reply language from the turn's language tag. Romanized Sinhala words are tagged SI, so Singlish got Sinhala-script replies. The reply now follows the characters the user typed.

**Limits seen (model, not policy):**
- **A complaint in the middle of a conversation is not detected.** After two passport turns, the window_3 input makes the complaint text `passport_new` at 0.77, so it never reaches the complaint rule (also noted in technicalWorkFlow §7).
- **An unsure first message can lock.** "mata udaw ekak one" ("I need help") is `nic_new` at 0.63, above the first-turn threshold, so the bot asks for a district instead of "which service?".
- **The no-switch rule is strict.** A user who changes service while a slot question is pending is not switched; they can switch on a later turn.

**Not measured yet.** The policy changes multi-turn behaviour, but `dst_eval.py` scores the tracker directly, not `Session`, so Observations 9–10 are unchanged. Next: run the gold and fresh dialogues through `Session` and compare JGA with and without the policy.

Tests: 17 in `service/tests/test_intent_policy.py`, using a fake model that misreads every follow-up turn. 66 service tests in total, all passing.
 
