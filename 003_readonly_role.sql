-- 003_readonly_role.sql — read-only role for the LLM agent. Idempotent: safe to re-run. (renamed from readonly_role.sql)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'appdb_reader') THEN
        CREATE ROLE appdb_reader WITH LOGIN;
    END IF;
END
$$;

GRANT CONNECT ON DATABASE appdb TO appdb_reader;
GRANT USAGE ON SCHEMA public TO appdb_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO appdb_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO appdb_reader;
