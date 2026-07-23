import os
import sys
import json
import importlib
from dotenv import load_dotenv
import psycopg
from psycopg import sql
from agent import ask_agent

load_dotenv(encoding="utf-8-sig")

CASES_MODULE = sys.argv[1] if len(sys.argv) > 1 else "eval_cases"
EVAL_CASES = importlib.import_module(CASES_MODULE).EVAL_CASES

LOG_PATH = "logs/tool_calls.jsonl"


def _log_line_count():
    if not os.path.exists(LOG_PATH):
        return 0
    with open(LOG_PATH) as f:
        return sum(1 for _ in f)


def _new_log_entries(start_line):
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
        cur.execute(sql.SQL("DROP TABLE IF EXISTS agent_scratch.{}").format(sql.Identifier(table_name)))
    conn.commit()
    conn.close()


results = []
for case in EVAL_CASES:
    start_line = _log_line_count()
    response = ask_agent(case["question"])
    new_entries = _new_log_entries(start_line)

    tools_called = sorted({entry["tool_name"] for entry in new_entries})
    tool_ok = case["expected_tool"] in tools_called

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
