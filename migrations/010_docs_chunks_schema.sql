-- 010_docs_chunks_schema.sql — chunk storage for Build 3.5's documentation RAG agent.
-- Depends on the vector extension (enabled in Build 3, Phase 1).
CREATE SCHEMA IF NOT EXISTS docs;

CREATE TABLE IF NOT EXISTS docs.chunks (
    chunk_id SERIAL PRIMARY KEY,
    source_file TEXT NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding vector(384)
);

GRANT USAGE ON SCHEMA docs TO appdb_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA docs TO appdb_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA docs GRANT SELECT ON TABLES TO appdb_reader;
