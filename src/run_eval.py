import os
import sys
import json
import importlib
from dotenv import load_dotenv
import psycopg
from psycopg import sql
from agent import ask_agent

load_dotenv(encoding="utf-8-sig")

# Lets a new round of cases (e.g. eval_cases_round2) run via `python run_eval.py <module>`
# without editing this file - see eval_cases_round2.py for the first case added this way.
CASES_MODULE = sys.argv[1] if len(sys.argv) > 1 else "eval_cases"
EVAL_CASES = importlib.import_module(CASES_MODULE).EVAL_CASES

LOG_PATH = "logs/tool_calls.jsonl"


def _log_line_count():
    if not os.path.exists(LOG_PATH):
        return 0
    with open(LOG_PATH) as f:
        return sum(1 for _ in f)


def _new_log_entries(start_line):
    # Reuses Phase 1's tool-call log as the source of truth for "what did the agent actually
    # call," rather than having ask_agent() return tool-call metadata itself - avoids
    # duplicating tracking logic that already exists, and proves Phase 1 pays for itself.
    with open(LOG_PATH) as f:
        lines = f.readlines()[start_line:]
    return [json.loads(line) for line in lines]


def _cleanup(table_name):
    conn = psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=5432,
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_AGENT_WRITER_USER"],
        password=os.environ["POSTGRES_AGENT_WRITER_PASSWORD"],
    )
    with conn.cursor() as cur:
        # table_name only ever comes from trusted eval_cases.py, so this isn't defending
        # against a real injection risk here - it matches tools.py's save_dataframe
        # convention on purpose, so this project doesn't have two different ways to
        # build a dynamic identifier safely.
        cur.execute(sql.SQL("DROP TABLE IF EXISTS agent_scratch.{}").format(sql.Identifier(table_name)))
    conn.commit()
    conn.close()


results = []
for case in EVAL_CASES:
    # ci_skip cases genuinely can't be tested in CI: this round's "previously saved result"
    # case depends on eval_domain_avg_duration surviving from round 1's save-case earlier in
    # the same job - but round 1's own cleanup_table step drops that table immediately after
    # its case runs (needed for round 1 to stay idempotent/rerunnable on its own), so nothing
    # is ever left for this case to find in a genuinely fresh environment. Locally it can look
    # like it passes only by coincidence, if agent_scratch happens to still hold an unrelated
    # leftover table from past manual testing - not a real signal either way, hence skipped
    # here rather than left to fail (or pass) unpredictably.
    if case.get("ci_skip") and os.environ.get("CI") == "true":
        print(f"\n[SKIPPED - CI] {case['question']}")
        continue

    start_line = _log_line_count()
    response = ask_agent(case["question"])
    new_entries = _new_log_entries(start_line)

    # new_entries also includes the log_final_answer/log_verification entries every question
    # now produces (Build 6/Build 7) - neither carries tool_name, so this must filter to only
    # the real tool-call entries first. Same "tool_name" in entry check logging_utils.py and
    # view_recent_questions.py already use to tell the log's entry shapes apart. Found 2026-08-05
    # the first time this eval job ran against that logging shape at all - it's been broken
    # since log_final_answer was added, just never actually exercised in CI until now.
    tools_called = sorted({entry["tool_name"] for entry in new_entries if "tool_name" in entry})
    # expected_tool can be a single tool name (most cases - one clear right answer) or a list
    # (a case where several different tools are all legitimate ways to reach the same correct
    # conclusion, e.g. discovering a question is out of scope - checking one exact tool would
    # itself be a flaky assertion, confirmed live 2026-08-06 when the same question grounded
    # itself via list_tables most of the time but search_docs or run_sql_query some runs).
    expected_tools = case["expected_tool"] if isinstance(case["expected_tool"], list) else [case["expected_tool"]]
    tool_ok = any(t in tools_called for t in expected_tools)

    # Strips commas so "1,243" still matches an expected_keywords entry of "1243" - found
    # necessary live when a round-2 case's real answer used comma-formatted numbers.
    answer_lower = response["answer"].lower().replace(",", "")
    keywords_ok = all(kw.lower() in answer_lower for kw in case["expected_keywords"])

    passed = tool_ok and keywords_ok and response["error"] is None

    if "cleanup_table" in case:
        _cleanup(case["cleanup_table"])

    results.append({
        "question": case["question"],
        "passed": passed,
        "tool_ok": tool_ok,
        "tools_called": tools_called,
        "keywords_ok": keywords_ok,
        "answer": response["answer"],
        "error": response["error"],
    })

print("\n" + "=" * 70)
print("EVAL REPORT")
print("=" * 70)
for r in results:
    status = "PASS" if r["passed"] else "FAIL"
    print(f"\n[{status}] {r['question']}")
    print(f"  tools called: {r['tools_called']} (tool_ok={r['tool_ok']})")
    print(f"  keywords_ok: {r['keywords_ok']}")
    if r["error"]:
        print(f"  error: {r['error']}")
    print(f"  answer: {r['answer'][:200]}")

passed_count = sum(1 for r in results if r["passed"])
print("\n" + "=" * 70)
print(f"{passed_count}/{len(results)} passed")
print("=" * 70)

# Previously always exited 0 regardless of pass/fail - fine for a human reading the printed
# report locally, but it means the new CI eval job (Build 5 Phase 3) could never actually go
# red on a real regression, only on a crash. A non-zero exit on any failure is what makes this
# job meaningfully gate a merge to main rather than just running silently.
if passed_count < len(results):
    sys.exit(1)
