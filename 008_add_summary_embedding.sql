-- 008_add_summary_embedding.sql — adds a pgvector embedding column for clean.allocations.summary.
-- Depends on the vector extension (enabled Phase 1, step 1) and clean.allocations already existing.

ALTER TABLE clean.allocations
    ADD COLUMN IF NOT EXISTS summary_embedding vector(384);