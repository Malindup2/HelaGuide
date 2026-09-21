# 0002 · Neo4j for public knowledge, PostgreSQL for citizen data

**Status:** accepted

**Context.** The knowledge graph holds public facts scraped from government sites and
may be exposed through an API. The system also holds per-citizen state: sessions,
feedback, preferences.

**Decision.** Two stores. Neo4j holds only public service knowledge, written only by
C2. PostgreSQL holds citizen data, one schema per owning component.

**Consequences.** No export or API call on the graph can leak personal data. Citizen
data is deletable with a plain `DELETE`. Sessions are anonymous; no names or NIC
numbers are stored.
