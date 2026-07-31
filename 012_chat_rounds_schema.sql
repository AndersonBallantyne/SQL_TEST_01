-- 012_chat_rounds_schema.sql — durable storage for the shared chat feed (Build 6 Phase 3.5,
-- persistent chat history). One global conversation (Option B) - not per-session/per-user.
-- Lives in agent_scratch since it's the agent's own conversational memory, just persisted by
-- the application layer instead of a save_dataframe tool call - reuses appdb_agent_writer
-- rather than creating a third role. Deliberately excluded from list_tables()/describe_table()
-- discovery in tools.py, same housekeeping principle as removing customers/orders.

CREATE TABLE IF NOT EXISTS agent_scratch.chat_rounds (
    round_id BIGSERIAL PRIMARY KEY,
    question_id TEXT NOT NULL,
    user_question TEXT NOT NULL,
    answer_text TEXT NOT NULL,
    full_messages JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- DELETE included from the start (amended after the fact - see MAX_CHAT_ROUNDS in tools.py,
-- added once the table had no retention cap at all): save_chat_round() trims the oldest rows
-- past MAX_CHAT_ROUNDS right after each insert, which needs DELETE, not just SELECT/INSERT.
GRANT SELECT, INSERT, DELETE ON agent_scratch.chat_rounds TO appdb_agent_writer;
GRANT USAGE ON SEQUENCE agent_scratch.chat_rounds_round_id_seq TO appdb_agent_writer;
GRANT SELECT ON agent_scratch.chat_rounds TO appdb_reader;
