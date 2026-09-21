# Identifier conventions

These strings appear in every component. Agree them once, never change them casually.

| Identifier | Format | Example |
|---|---|---|
| Service | `svc:<service_slug>` | `svc:passport`, `svc:nic` |
| Fact | `<service_id>:<predicate>[:<qualifier>]` | `svc:passport:fee:normal` |
| Session | `anon-<random>` | `anon-7f3c` |

Slugs are lowercase `snake_case`, ASCII only.

Allowed predicates: `fee`, `document`, `agency`, `prerequisite`, `processing_time`, `eligibility`.

## The one rule that matters

**A `fact_id` is derived from where the fact sits in the graph, never from its value.**

When the passport fee changes from 10,000 to 11,000, the fact keeps the id
`svc:passport:fee:normal`. C2 closes the old version's `valid_to` and opens a
new version. If the id were derived from the value, every correction would look
like a new fact and C3 could never attach a report to "this specific fact".

## Who owns the service vocabulary

C2 publishes the list of valid `service_id`s. C1 must map free text onto that
list, not invent its own. If C1 emits `svc:passport_application` and the graph
holds `svc:passport`, nothing matches.
