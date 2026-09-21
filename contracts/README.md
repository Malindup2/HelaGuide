# Contracts

The interface between the four components. **This folder is owned by the whole team.**
Any change needs approval from every component owner, because it breaks someone.

## Flows

| Schema | From | To | When |
|---|---|---|---|
| `intent` | C1 | C2 | Every citizen request |
| `plan` | C2 | C4 | Every citizen request |
| `render` | C4 | gateway, frontend | Every citizen request |
| `feedback` | C4 | C3 | A citizen reports a problem |
| `trust` | C3 | C4 | Shown as a warning on disputed facts |
| `correction` | C3 | C2 | C3 has verified a correction |
| `fact` | C2 | C3 | C3 looks up a fact and its history |

## Rules

- Schemas are JSON Schema draft 2020-12, in `schema/v1/`.
- Every schema has one valid sample in `examples/`. CI checks each sample against its schema.
- Examples are **illustrative**. The fee values are placeholders, not authoritative figures.
- Breaking change → new folder `schema/v2/`. Never edit a released schema in place.
- Pydantic mirrors live in `shared/helaguide_common/contracts.py`. Keep them in step.

Validate locally:

```bash
python scripts/validate_contracts.py
```
