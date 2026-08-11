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
        # one thing any correct answer must contain regardless of wording. Question
        # reworded 2026-08-06 (was the open-ended "why does...") to directly ask for
        # both role names, not just the reasoning - a directive question makes the
        # model far more likely to state both literal identifiers up front rather than
        # burying them in paraphrased prose. Confirmed live: 4/5 with the new wording
        # vs. a real failure the same day with the old one. Not airtight (a substring
        # check on free text never fully is), but a real, measured improvement.
        # expected_tool widened to a list 2026-08-10, CI run 31449449929: failed on
        # tool_ok alone (keywords_ok was True, answer fully correct) - the model used
        # run_sql_query against docs.chunks instead of search_docs, following the
        # SYSTEM_PROMPT's own "what are the X" routing rule (2026-08-07) literally.
        # The last green eval run (0ed4f11) called search_docs for this same question;
        # both paths reach docs.chunks content and both are intentional per the prompt -
        # not a regression, an eval case never updated after that routing rule widened.
        "question": "What are the names of agent_scratch's two database roles, and why are there two instead of one?",
        "expected_tool": ["search_docs", "run_sql_query"],
        "expected_keywords": ["appdb_reader", "appdb_agent_writer"],
    },
    {
        # expected_tool widened to a list for the same reason and same CI run as the case
        # above. "What kind of X" is a category question, and the SYSTEM_PROMPT's own rule
        # for individual-item questions (added 2026-08-07) deliberately routes category/type
        # questions to clean.allocation_items via run_sql_query instead of search_summaries -
        # confirmed live, that path's answer was fully correct and better-organized (split
        # camera bodies from accessories via is_accessory) than semantic search alone would
        # produce. describe_table included too: the model queried the schema first, on this
        # run, before writing the SQL - not itself the point of this case, but a legitimate
        # step in reaching a correct run_sql_query answer.
        "question": "What kind of camera equipment has been checked out recently?",
        "expected_tool": ["search_summaries", "run_sql_query", "describe_table"],
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
        # Stale since Build 6 removed customers/orders from the agent's discovery scope
        # entirely (confirmed 2026-08-06: agent.py's SYSTEM_PROMPT has zero live mention of
        # either table) - there is no revenue concept clean.allocations can ever answer, so
        # the correct behavior is recognizing that and redirecting, never fabricating a "$"
        # figure. expected_tool is a list, not one tool: the agent reaches that correct
        # conclusion via list_tables most runs, but search_docs or run_sql_query some runs -
        # all three are legitimate grounding paths to the same right answer. "allocations" is
        # the stable keyword every observed correct answer redirects to, verified live 4/4.
        "question": "What's the total revenue from all orders?",
        "expected_tool": ["list_tables", "search_docs", "run_sql_query"],
        "expected_keywords": ["allocations"],
    },
    {
        # First hit MAX_TOOL_TURNS entirely (describe_table('docs.chunks') silently returned
        # [] - see tools.py) before ever answering; once that was fixed, it still failed
        # because "docs.chunks" (the original keyword) is an internal table name no correct
        # prose answer would ever say back to the user. Real filenames, first/last in
        # sequence, catch truncation too - the "last" keyword needs updating each time a new
        # migration lands (was 009, now 013 after 2026-08-06's allocation_items normalization),
        # or it stops actually testing for truncation of the current full list.
        "question": "List all the SQL migration files used in this project.",
        "expected_tool": "run_sql_query",
        "expected_keywords": ["001_schema.sql", "013_allocation_items_schema.sql"],
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
