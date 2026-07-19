-- 004_raw_schema.sql — PostgreSQL raw staging schema for Build 2 (raw-to-queryable pipeline) (renamed from raw_schema.sql)
-- Running this REBUILDS the raw layer from scratch. It drops existing data first,
-- which is what you want for a clean, reproducible setup. Re-run ingest.py afterward
-- to reload the CSV.

CREATE SCHEMA IF NOT EXISTS raw;

DROP TABLE IF EXISTS raw.allocations;

CREATE TABLE raw.allocations (
    allocation_id     TEXT,
    patron_department TEXT,
    patron_email       TEXT,
    renewal_count      TEXT,
    actual_start        TEXT,
    scheduled_end       TEXT,
    actual_end           TEXT,
    duration             TEXT,
    resource_count       TEXT,
    summary              TEXT
);


-- Grant the read-only agent role access to this schema. Assumes appdb_reader
-- already exists (created by readonly_role.sql) — run that first on a fresh volume.
GRANT USAGE ON SCHEMA raw TO appdb_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA raw TO appdb_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA raw GRANT SELECT ON TABLES TO appdb_reader;
