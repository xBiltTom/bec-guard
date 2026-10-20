-- Executed once, when PostgreSQL initializes an empty data volume.
-- Business tables are intentionally not created in Phase 1.
CREATE SCHEMA IF NOT EXISTS n8n;
