-- 015_demo_token_log.sql — a hard daily token-spend cap for the public Streamlit Community
-- Cloud demo (src/app_demo.py), so a public link with no login can't turn into an unbounded
-- API bill. INSERT-only, one row per question, same pattern as table_metadata (013): the check
-- is SUM(tokens_used) WHERE logged_at::date = CURRENT_DATE, computed at read time, rather than
-- a single running-total row that would need UPDATE - appdb_agent_writer gets INSERT only,
-- matching the real code path (it only ever appends, never edits a past day's total).
-- Local docker-compose deployment never touches this table at all - src/app.py has no daily
-- cap and isn't meant to (single trusted operator, not a public link).

CREATE TABLE IF NOT EXISTS agent_scratch.demo_token_log (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    logged_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    tokens_used BIGINT NOT NULL
);

GRANT SELECT, INSERT ON agent_scratch.demo_token_log TO appdb_agent_writer;
GRANT SELECT ON agent_scratch.demo_token_log TO appdb_reader;
GRANT USAGE ON SEQUENCE agent_scratch.demo_token_log_id_seq TO appdb_agent_writer;
