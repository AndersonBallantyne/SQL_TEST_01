# Every expected_keywords value here was pulled via a direct run_sql_query against the DB
# before being written, not copied from the agent's own first answer - a stronger,
# independent check than eval_cases.py mostly used, since it doesn't risk the eval and the
# agent being wrong the same way.
EVAL_CASES = [
    {
        # "named" steers toward excluding NULL patron_department - raw ground truth has 787
        # NULL rows outranking every real department; the question is about a real one.
        # Was "ILLU" (128 rows, real ground truth) before Build 5's data-anonymization pass -
        # DEPARTMENT_MAP (synthesize_dataset.py) remaps it 1:1 to "DRAW", same row-for-row
        # membership so the count and plurality are unchanged, just the code string.
        "question": "Which named patron department has the most recorded allocations?",
        "expected_tool": "run_sql_query",
        "expected_keywords": ["DRAW"],
    },
    {
        # Was "How many customers are in the database?" - genuinely ambiguous once the
        # legacy customers table left scope (2026-07-30, SYSTEM_PROMPT's "ignore any
        # unrelated seed tables" line): "customer" has no real column to map to, so the
        # model non-deterministically picked either patron_email_domain (4, intended) or
        # patron_department (16) - confirmed flaky via 3 live re-runs, 2/3 vs 1/3, not a
        # one-off. Reworded to name the actual column so there's nothing left to guess.
        "question": "How many distinct patron email domains are there?",
        "expected_tool": "run_sql_query",
        "expected_keywords": ["4"],
    },
    {
        # Genuinely CI-incompatible, confirmed by two live CI runs (2026-07-24): this depends
        # on eval_domain_avg_duration surviving from round 1's save-case, but round 1's own
        # cleanup_table step drops it immediately after that case runs, before round 2 ever
        # executes - see run_eval.py's ci_skip handling for the full explanation.
        "question": "Do you have a previously saved result about average allocation duration by email domain? If so, which domain had the longest average duration?",
        "expected_tool": "run_sql_query",
        "expected_keywords": ["gmail.com"],
        "ci_skip": True,
    },
    {
        "question": "How many allocations were never renewed (a renewal_count of zero)?",
        "expected_tool": "run_sql_query",
        "expected_keywords": ["1243"],
    },
    {
        # Deliberately equipment that doesn't exist in the dataset - tests that
        # search_summaries' graceful "no match" message survives into the final answer
        # instead of the model hallucinating a fake result. expected_keywords is empty on
        # purpose: the exact "no match" phrasing isn't the point, tool_ok + no error is.
        "question": "Is there any scuba diving equipment among the allocations?",
        "expected_tool": "search_summaries",
        "expected_keywords": [],
    },
]
