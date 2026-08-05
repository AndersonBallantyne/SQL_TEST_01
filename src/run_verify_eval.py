import sys
from verify_answer import verify_answer
from verify_eval_cases import VERIFY_EVAL_CASES

def run():
    failures = 0
    for case in VERIFY_EVAL_CASES:
        supported, reason = verify_answer(case["user_question"], case["answer"], case["tool_calls"])
        passed = supported == case["expected_supported"]
        print(f"[{'PASS' if passed else 'FAIL'}] {case['description']}")
        print(f"  expected_supported={case['expected_supported']}  actual_supported={supported}")
        print(f"  reason: {reason}\n")
        if not passed:
            failures += 1

    total = len(VERIFY_EVAL_CASES)
    print(f"{total - failures}/{total} cases passed")
    if failures:
        sys.exit(1)

if __name__ == "__main__":
    run()

