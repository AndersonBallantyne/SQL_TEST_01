-- 011_metrics_history_schema.sql — Build 4 follow-up: a queryable history of metrics_rollup.py
-- runs, addressing the "one-shot snapshot, not a tracked time series" limitation.
-- Separate from agent_scratch on purpose: this is written by a human-run maintenance script
-- (metrics_rollup.py, connecting as the admin role, same pattern as ingest.py/embed_summaries.py),
-- not by the agent itself at runtime - agent_scratch is specifically the agent's own workspace.

CREATE SCHEMA IF NOT EXISTS observability;

CREATE TABLE IF NOT EXISTS observability.metrics_history (
    id                      SERIAL PRIMARY KEY,
    run_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    total_calls             INTEGER NOT NULL,
    total_questions         INTEGER NOT NULL,
    avg_turns_per_question  NUMERIC(6,2) NOT NULL,
    error_count             INTEGER NOT NULL,
    error_rate              NUMERIC(6,4) NOT NULL,
    tool_usage              JSONB NOT NULL
);

GRANT USAGE ON SCHEMA observability TO appdb_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA observability TO appdb_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA observability GRANT SELECT ON TABLES TO appdb_reader;
