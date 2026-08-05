# Each case: hand-constructed evidence + a proposed answer, checked directly against
# verify_answer() rather than the live log - reproducible and CI-portable, same lesson
# Build 5 learned the hard way about depending on real historical state. All three cases
# use clean.allocations, the agent's actual in-scope table - customers/orders were removed
# from list_tables()/describe_table() discovery, so the live agent can no longer produce
# a scenario involving them.
VERIFY_EVAL_CASES = [
    {
        "description": "grounded answer matches real evidence",
        "user_question": "How many allocations have renewal_count = 0?",
        "tool_calls": [
            {
                "tool_name": "run_sql_query",
                "input": {"sql": "SELECT COUNT(*) FROM clean.allocations WHERE renewal_count = 0"},
                "output": [{"count": 1243}],
            }
        ],
        "answer": "There are 1,243 allocations with a renewal_count of 0.",
        "expected_supported": True,
    },
    {
        "description": "answer contradicts the evidence outright",
        "user_question": "Is there any camera equipment in the inventory?",
        "tool_calls": [
            {
                "tool_name": "run_sql_query",
                "input": {"sql": "SELECT summary FROM clean.allocations WHERE summary ILIKE '%camera%' LIMIT 2"},
                "output": [
                    {"summary": "NIKON Z6 III MIRRORLESS BODY - NIKON Z6III-100001"},
                    {"summary": "FUJIFILM X-T5 BODY - FUJI XT5-100002"},
                ],
            }
        ],
        "answer": "There is no camera equipment available in the inventory.",
        "expected_supported": False,
    },
    {
        "description": "answer invents a number the evidence never returned",
        "user_question": "What's the total dollar value of equipment checked out?",
        "tool_calls": [
            {
                "tool_name": "run_sql_query",
                "input": {"sql": "SELECT summary FROM clean.allocations LIMIT 5"},
                "output": [{"summary": "MACBOOK AIR M3 LAPTOP - MBA M3-100003"}],
            }
        ],
        "answer": "The total dollar value of equipment checked out is approximately $48,500.",
        "expected_supported": False,
    },
]
