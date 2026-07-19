-- raw_schema.sql — PostgreSQL raw staging schema for Build 2 (raw-to-queryable pipeline)
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
