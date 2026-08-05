-- 009_add_summary_embedding_hnsw_index.sql — adds an HNSW approximate-nearest-neighbor
-- index on clean.allocations.summary_embedding, so search_summaries' cosine-distance
-- query (<=>) can use an index scan instead of a full sequential scan as the table grows.
-- Depends on 008_add_summary_embedding.sql (the column) and the vector extension.
CREATE INDEX IF NOT EXISTS idx_allocations_summary_embedding_hnsw
    ON clean.allocations
    USING hnsw (summary_embedding vector_cosine_ops);
