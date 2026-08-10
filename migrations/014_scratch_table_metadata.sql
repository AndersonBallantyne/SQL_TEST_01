-- 014_scratch_table_metadata.sql — creation-time tracking for agent_scratch tables, closing
-- half of a deliberately-deferred gap (Build 2.5): "no cleanup policy for scratch tables...
-- automated expiry would be over-engineering for what's currently a single-agent, low-volume
-- workspace." Revisited 2026-08-10 - not because the traffic profile changed, but because
-- "manual DROP TABLE is fine" only works if there's an easy way to tell which tables are
-- actually stale. This table makes age visible; it doesn't make cleanup automatic on its own -
-- src/cleanup_scratch_tables.py still requires an explicit --execute flag to drop anything.
-- Age only, not "last use" - Postgres doesn't track object access time without extra
-- instrumentation, and for a workspace this size, "when was it created" is a reasonable proxy;
-- last-use tracking is a deliberate, noted simplification, not a silently dropped requirement.

CREATE TABLE IF NOT EXISTS agent_scratch.table_metadata (
    table_name TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Same reasoning as chat_rounds (012): the agent's own bookkeeping, not domain data - excluded
-- from list_tables()/describe_table() discovery in tools.py, same as chat_rounds already is.
GRANT SELECT, INSERT, DELETE ON agent_scratch.table_metadata TO appdb_agent_writer;
GRANT SELECT ON agent_scratch.table_metadata TO appdb_reader;
