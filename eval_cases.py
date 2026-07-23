EVAL_CASES = [
    {
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
        "question": "List all the SQL migration files used in this project.",
        "expected_tool": "run_sql_query",
        "expected_keywords": ["001_schema.sql", "009_add_summary_embedding_hnsw_index.sql"],
    },
    {
        "question": "What's the average allocation duration, in hours, grouped by patron email domain? Save this result for later as eval_domain_avg_duration.",
        "expected_tool": "save_dataframe",
        "expected_keywords": ["saved"],
        "cleanup_table": "eval_domain_avg_duration",
    },
]
