# expected_keywords should assert on stable identifiers (filenames, table/role names, exact
# numbers) the answer is structurally required to contain - not on how the model is likely to
# phrase a synthesized explanation. Free-text paraphrase varies run to run even when the
# answer is fully correct; two cases below were rewritten after failing this way live.
#
# Touched deliberately, 2026-07-24, to trigger Build 5 Phase 3's gated eval CI job for real -
# comment-only, no behavior change, verifying the "runs on a relevant merge to main" half of
# the gate (the "skips unrelated pushes" half was already confirmed by the previous push).
EVAL_CASES = [
    {
        # Originally ["blast radius", "audit"] - failed on a re-run whose answer was
        # completely correct but never used either exact phrase. Role names are the
        # one thing any correct answer must contain regardless of wording.
        "question": "Why does agent_scratch have two separate database roles?",
        "expected_tool": "search_docs",
        "expected_keywords": ["appdb_reader", "appdb_agent_writer"],
    },
    {
        "question": "What kind of camera equipment has been checked out recently?",
        "expected_tool": "search_summaries",
        "expected_keywords": ["camera"],
    },
    {
        "question": "What tables are available in this database?",
        "expected_tool": "list_tables",
        "expected_keywords": ["allocations"],
    },
    {
        "question": "What columns does the clean.allocations table have?",
        "expected_tool": "describe_table",
        "expected_keywords": ["patron_department", "duration_seconds"],
    },
    {
        "question": "What's the total revenue from all orders?",
        "expected_tool": "run_sql_query",
        "expected_keywords": ["$"],
    },
    {
        # First hit MAX_TOOL_TURNS entirely (describe_table('docs.chunks') silently returned
        # [] - see tools.py) before ever answering; once that was fixed, it still failed
        # because "docs.chunks" (the original keyword) is an internal table name no correct
        # prose answer would ever say back to the user. Real filenames, first/last in
        # sequence, catch truncation too.
        "question": "List all the SQL migration files used in this project.",
        "expected_tool": "run_sql_query",
        "expected_keywords": ["001_schema.sql", "009_add_summary_embedding_hnsw_index.sql"],
    },
    {
        # cleanup_table uses a distinct eval-only name (not the real domain_avg_duration
        # saved during Build 2.5 testing) so this case is rerunnable without colliding with
        # or clobbering existing scratch data - mirrors test_agent_scratch_boundary.py's
        # create-verify-drop pattern.
        "question": "What's the average allocation duration, in hours, grouped by patron email domain? Save this result for later as eval_domain_avg_duration.",
        "expected_tool": "save_dataframe",
        "expected_keywords": ["saved"],
        "cleanup_table": "eval_domain_avg_duration",
    },
]
