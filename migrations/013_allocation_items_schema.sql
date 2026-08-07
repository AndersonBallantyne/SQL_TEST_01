-- 013_allocation_items_schema.sql — normalizes clean.allocations.summary (one pipe-delimited
-- text blob per checkout, e.g. "Returned: ITEM - TAG | ITEM - TAG | ...") into one row per item,
-- with an explicit category/is_accessory/is_returned already resolved at load time.
--
-- This replaces query-time guesswork that was previously living in agent.py's SYSTEM_PROMPT:
-- keyword-based category matching (e.g. "CAMERA CASE" contains "CAMERA" but isn't one),
-- inconsistent model naming ("... BODY" vs "... CAMERA" for the same product class), and the
-- "Returned: " prefix living once on the whole summary string rather than per item. Confirmed
-- these were real, recurring correctness/cost problems in production use, not hypothetical -
-- see project memory, 2026-08-06 token-burn investigation.
--
-- Populated by src/build_allocation_items.py, not by SQL - classifying each of the ~55 distinct
-- item names into a category/is_accessory pair is a one-time lookup-table decision, not something
-- expressible as a migration alone. Depends on clean.allocations already being populated
-- (005_clean_schema.sql, run via src/transform.py).

CREATE TABLE IF NOT EXISTS clean.allocation_items (
    allocation_item_id  SERIAL PRIMARY KEY,
    allocation_id       TEXT NOT NULL REFERENCES clean.allocations(allocation_id),
    item_name           TEXT NOT NULL,
    category             TEXT NOT NULL,
    is_accessory          BOOLEAN NOT NULL,
    is_returned             BOOLEAN NOT NULL,
    tag                      TEXT
);

CREATE INDEX IF NOT EXISTS idx_allocation_items_allocation_id ON clean.allocation_items(allocation_id);
CREATE INDEX IF NOT EXISTS idx_allocation_items_category ON clean.allocation_items(category);

GRANT SELECT ON clean.allocation_items TO appdb_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA clean GRANT SELECT ON TABLES TO appdb_reader;
