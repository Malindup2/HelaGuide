# Contributing to HelaGuide

## Ownership

Each member owns one folder under `components/`. You can structure your own folder
however you like. You do not change anyone else's folder without their approval;
CODEOWNERS enforces this on pull requests.

| Folder | Owner |
|---|---|
| `components/c1-intent/` | Dabarera W. A. S. |
| `components/c2-knowledge-graph/` | T. Malindu Pabasara |
| `components/c3-trust/` | J. D. Minuli Pabasara |
| `components/c4-presentation/` | Dias K. S. S. |
| `frontend/` | Dias K. S. S. |
| `contracts/`, `shared/`, `docs/` | Everyone |

## Branches

- `main` is protected. No direct pushes.
- Branch per piece of work: `c2/change-classifier`, `c1/rasa-tracker`, `contracts/v1-plan-fields`.
- Merge by pull request once CI passes.

## Commits

Short, present tense, prefixed with the area:

```
c2: add DOM structure signature to fingerprint
contracts: add eligibility predicate
gateway: fetch trust scores in parallel
```

## Changing the contract

`contracts/` is the one place a change can break all four components.

1. Open a PR that touches `contracts/` only, plus the matching model in
   `shared/helaguide_common/contracts.py`.
2. Every component owner approves.
3. Breaking changes go in a new `schema/v2/`; never edit a released schema in place.

## Files that must not be committed

- `.env`, API keys, passwords
- Datasets and raw crawls over a few MB: store them on the team drive and note the
  location in `components/<cN>/research/data/README.md`
- Model weights (`*.bin`, `*.safetensors`, `*.ckpt`)

## Large binary files

PDFs, Word, PowerPoint and images are tracked with Git LFS. Run once per machine:

```bash
git lfs install
```

## Personal data

Sessions are anonymous (`anon-xxxx`). Do not store names, NIC numbers, phone numbers
or addresses anywhere, including test data and logs.
