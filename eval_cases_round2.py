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
        "question": "How many customers are in the database?",
        "expected_tool": "run_sql_query",
        "expected_keywords": ["4"],
    },
    {
        "question": "Do you have a previously saved result about average allocation duration by email domain? If so, which domain had the longest average duration?",
        "expected_tool": "run_sql_query",
        "expected_keywords": ["gmail.com"],
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
