-- 007_agent_scratch_schema.sql — the agent's writable scratch schema for persisted findings.
-- Depends on appdb_agent_writer (006_agent_scratch_role.sql) and appdb_reader
-- (003_readonly_role.sql) already existing.

CREATE SCHEMA IF NOT EXISTS agent_scratch;

GRANT USAGE, CREATE ON SCHEMA agent_scratch TO appdb_agent_writer;

GRANT USAGE ON SCHEMA agent_scratch TO appdb_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA agent_scratch TO appdb_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE appdb_agent_writer IN SCHEMA agent_scratch
    GRANT SELECT ON TABLES TO appdb_reader;
