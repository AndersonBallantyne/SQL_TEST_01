EVAL_CASES = [
    {
        "question": "Which named patron department has the most recorded allocations?",
        "expected_tool": "run_sql_query",
        "expected_keywords": ["ILLU"],
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
        "question": "Is there any scuba diving equipment among the allocations?",
        "expected_tool": "search_summaries",
        "expected_keywords": [],
    },
]
