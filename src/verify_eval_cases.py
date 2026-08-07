# Each case: hand-constructed evidence + a proposed answer, checked directly against
# verify_answer() rather than the live log - reproducible and CI-portable, same lesson
# Build 5 learned the hard way about depending on real historical state. All cases use
# clean.allocations, the agent's actual in-scope table - customers/orders were removed
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
    # Found live, 2026-08-06 (question_id edbce40d1a73, "How many cameras do you have?") -
    # the verifier's first version flagged this correctly (a real inconsistency: two of the
    # five per-model counts individually exceed the 350-row total, meaning they cannot be
    # valid subsets of it), but for the wrong stated reason ("these numbers don't add up").
    # A prompt fix that only taught "overlapping sums exceeding a total are fine" made this
    # a false negative instead - it has to still catch this exact shape while ALSO passing
    # the true-overlap case below where sums exceed the total for a legitimate reason.
    {
        "description": "per-category counts include ones broader than the total they're compared against (real regression case)",
        "user_question": "How many cameras do you have?",
        "tool_calls": [
            {
                "tool_name": "run_sql_query",
                "input": {"sql": "SELECT COUNT(DISTINCT summary) as unique_camera_entries FROM clean.allocations WHERE summary ILIKE '%camera%'"},
                "output": [{"unique_camera_entries": 350}],
            },
            {
                "tool_name": "run_sql_query",
                "input": {
                    "sql": "SELECT (SELECT COUNT(*) FROM clean.allocations WHERE summary ILIKE '%PANASONIC S5%') as panasonic_checkouts, "
                           "(SELECT COUNT(*) FROM clean.allocations WHERE summary ILIKE '%FUJIFILM X-T5%') as fujifilm_checkouts, "
                           "(SELECT COUNT(*) FROM clean.allocations WHERE summary ILIKE '%CAMERA%') as total_with_camera_keyword"
                },
                "output": [{"panasonic_checkouts": 375, "fujifilm_checkouts": 373, "total_with_camera_keyword": 350}],
            },
        ],
        "answer": "I found camera equipment in 350 checkout records. Panasonic S5 II: 375 checkouts, Fujifilm X-T5: 373 checkouts. Some checkouts include multiple camera models bundled together, so these counts overlap.",
        "expected_supported": False,
    },
    # The look-alike control case for the one above - same shape (per-category counts that
    # sum to more than a stated total, an answer that explains it as overlap), but here every
    # individual count is still <= the total, which is what makes overlap the correct and only
    # explanation. Confirms the fix didn't just learn "always distrust overlap explanations."
    {
        "description": "true overlap - individual counts each fit inside the total, sum exceeds it legitimately",
        "user_question": "How many checkouts include a laptop or a tablet?",
        "tool_calls": [
            {
                "tool_name": "run_sql_query",
                "input": {
                    "sql": "SELECT (SELECT COUNT(*) FROM clean.allocations WHERE summary ILIKE '%LAPTOP%') as laptop_checkouts, "
                           "(SELECT COUNT(*) FROM clean.allocations WHERE summary ILIKE '%TABLET%') as tablet_checkouts, "
                           "(SELECT COUNT(*) FROM clean.allocations WHERE summary ILIKE '%LAPTOP%' OR summary ILIKE '%TABLET%') as total_laptop_or_tablet"
                },
                "output": [{"laptop_checkouts": 120, "tablet_checkouts": 90, "total_laptop_or_tablet": 180}],
            },
        ],
        "answer": "120 checkouts included a laptop and 90 included a tablet. Some checkouts bundle both together, so these overlap - the total number of checkouts with a laptop and/or a tablet is 180.",
        "expected_supported": True,
    },
]
