-- 008_add_summary_embedding.sql — adds a pgvector embedding column for clean.allocations.summary.
-- Depends on clean.allocations already existing.

-- Previously enabled by hand, once, outside any committed file, on the author's own volume -
-- a real reproducibility gap only surfaced when a genuinely fresh volume (CI's throwaway
-- service container) tried to apply these migrations from scratch and failed on this exact
-- line ("type vector does not exist"). Idempotent, so safe on a volume where it's already on.
CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE clean.allocations
    ADD COLUMN IF NOT EXISTS summary_embedding vector(384);