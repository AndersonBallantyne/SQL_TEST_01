-- 007_agent_scratch_schema.sql — the agent's writable scratch schema for persisted findings.
-- Depends on appdb_agent_writer (006_agent_scratch_role.sql) and appdb_reader
-- (003_readonly_role.sql) already existing.

CREATE SCHEMA IF NOT EXISTS agent_scratch;

GRANT USAGE, CREATE ON SCHEMA agent_scratch TO appdb_agent_writer;

GRANT USAGE ON SCHEMA agent_scratch TO appdb_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA agent_scratch TO appdb_reader;
-- "FOR ROLE appdb_agent_writer" (not the plain "ALTER DEFAULT PRIVILEGES IN SCHEMA" form used
-- elsewhere) is what makes this apply to tables THAT ROLE creates later via save_dataframe -
-- the plain form only covers objects the current session's own role creates, which here would
-- be whoever ran this migration, not appdb_agent_writer. Without this, every future
-- save_dataframe table would need its own manual GRANT before appdb_reader could see it.
ALTER DEFAULT PRIVILEGES FOR ROLE appdb_agent_writer IN SCHEMA agent_scratch
    GRANT SELECT ON TABLES TO appdb_reader;
