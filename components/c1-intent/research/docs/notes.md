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

## Next steps
- [ ] Install Label Studio (env `label`)
- [ ] Define intent list and slots per intent (align with Knowledge Graph ontology)
- [ ] Write 50–100 seed dialogues (Sinhala script + Singlish, 1–5 turns, with corrections)
- [ ] Label seed data: token language tags, entities, intent
- [ ] Run fastText baseline on full seed set and log the result
