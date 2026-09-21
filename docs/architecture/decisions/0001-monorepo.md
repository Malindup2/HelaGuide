# 0001 · One repository for all four components

**Status:** accepted

**Context.** Four components developed separately and integrated later, sharing one
interface contract.

**Decision.** A single repository. Each component owns one folder under
`components/`; the contract lives at the root in `contracts/`.

**Consequences.** A contract change and the code that depends on it land in one pull
request, so no component is ever built against a stale version of another. CODEOWNERS
keeps each folder under its owner's review.
