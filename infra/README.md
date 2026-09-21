# infra

| Store | Holds | Writes | Reads |
|---|---|---|---|
| **Neo4j** | Public service knowledge: services, agencies, facts, versions | C2 only | C2, C3 |
| **PostgreSQL** | Private citizen data: sessions, feedback, trust, preferences | C1, C3, C4 | same |

The two are kept apart on purpose. The graph is public and may be exposed through an
API; citizen data must never travel with it, and must be deletable on request.

- `postgres/*.sql` runs automatically the first time the Postgres volume is created.
  To re-run it: `docker compose down -v` (this **deletes** local data).
- `neo4j/constraints.cypher` is applied by hand once; see the comment at the top of the file.
