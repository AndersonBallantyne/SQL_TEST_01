-- 006_agent_scratch_role.sql — writable role for the agent's scratch workspace. Idempotent: safe to re-run.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'appdb_agent_writer') THEN
        CREATE ROLE appdb_agent_writer WITH LOGIN;
    END IF;
END
$$;

GRANT CONNECT ON DATABASE appdb TO appdb_agent_writer;
