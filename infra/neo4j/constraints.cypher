// HelaGuide knowledge graph constraints. Owned by C2; others read only.
// Apply once after the first start:
//   docker compose exec neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" -f /infra/constraints.cypher

CREATE CONSTRAINT service_id IF NOT EXISTS
FOR (s:Service) REQUIRE s.service_id IS UNIQUE;

CREATE CONSTRAINT agency_id IF NOT EXISTS
FOR (a:Agency) REQUIRE a.agency_id IS UNIQUE;

// One row per fact version; fact_id repeats across versions, so it is indexed, not unique.
CREATE INDEX fact_id IF NOT EXISTS
FOR (f:Fact) ON (f.fact_id);

CREATE INDEX fact_current IF NOT EXISTS
FOR (f:Fact) ON (f.fact_id, f.valid_to);

CREATE CONSTRAINT page_url IF NOT EXISTS
FOR (p:SourcePage) REQUIRE p.url IS UNIQUE;

// A downloadable form (PDF or Word) a service asks the citizen to fill in.
CREATE CONSTRAINT form_url IF NOT EXISTS
FOR (f:Form) REQUIRE f.url IS UNIQUE;

// A canonical document (birth_certificate, national_identity_card ...) shared by many services.
CREATE CONSTRAINT document_key IF NOT EXISTS
FOR (d:Document) REQUIRE d.document_key IS UNIQUE;
