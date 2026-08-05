-- 005_clean_schema.sql — PostgreSQL clean/typed schema for Build 2 (raw-to-queryable pipeline)
-- Running this REBUILDS the clean layer from scratch. Depends on the raw layer
-- (004_raw_schema.sql) already being populated — transform.py reads from it.
-- Also depends on appdb_reader already existing (003_readonly_role.sql).

CREATE SCHEMA IF NOT EXISTS clean;

DROP TABLE IF EXISTS clean.allocations;

CREATE TABLE clean.allocations (
    allocation_id        TEXT PRIMARY KEY,
    patron_department    TEXT,
    patron_email_domain  TEXT NOT NULL,
    renewal_count         INTEGER NOT NULL,
    actual_start           TIMESTAMP NOT NULL,
    scheduled_end           TIMESTAMP NOT NULL,
    actual_end               TIMESTAMP NOT NULL,
    duration_seconds          INTEGER GENERATED ALWAYS AS
        (EXTRACT(EPOCH FROM (actual_end - actual_start))::INTEGER) STORED,
    resource_count             INTEGER NOT NULL,
    summary                     TEXT
);

GRANT USAGE ON SCHEMA clean TO appdb_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA clean TO appdb_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA clean GRANT SELECT ON TABLES TO appdb_reader;
