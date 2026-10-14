# Data

Small files only (under a few MB). Large datasets, raw crawls and model weights stay
**out of git**. Store them on the team drive and record the location here:

| Dataset | Location | Owner | Notes |
|---|---|---|---|
| C3 PP1 mock data | `mock/` (in git, small) | Minuli | Everything the PP1 demo needs. No real citizen data, no data from other components. |

## What is in `mock/`

| File | What it is | Shape |
|---|---|---|
| `c2_facts.json` | The mock knowledge graph: 58 facts for 8 services of the Department for Registration of Persons, the Department of Immigration and Emigration and the Registrar General's Department. **Fee values are illustrative placeholders, not official figures.** | exactly C2's `fact` contract |
| `c2_facts_updates.json` | New versions C2 would publish on 28 Oct 2026 (used by the demo's "official value changes" step) | `fact` contract |
| `service_aliases.json` | Service names and aliases in English, Sinhala and Singlish | C3-private |
| `reporters.json` | 15 mock anonymous reporters with stable ids, account creation dates and reputation counters (`a`, `b`) | C3-private |
| `feedback_structured.json` | 8 messages in exactly the `feedback` contract (C4 -> C3) | `feedback` contract |
| `structured_extras.json` | Visit dates the contract message cannot carry | C3-private |
| `feedback_freetext.json` | 33 free-text messages (English, Sinhala, Singlish) as C1 would forward them | C3-private proposal, **not** in `contracts/` |
| `expected_labels.json` | The answer key: the correct outcome for each of the 41 messages, and a `tune` / `test` split | C3-private |
| `normalised_cache.json` | English translations of the Sinhala and Singlish messages (see below) | C3-private |

## Translations

`normalised_cache.json` starts with translations written by the project author (`"source": "authored"`).
`python -m app.cli.translate_cache --overwrite` replaces them with Gemini's (`"source": "gemini"`,
`"reviewed": false`). **Read them, fix mistakes by hand, set `"reviewed": true`.** Have a Sinhala speaker
check the Sinhala messages.
