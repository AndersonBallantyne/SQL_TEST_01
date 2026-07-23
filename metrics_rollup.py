import os
import json
from collections import Counter
from datetime import datetime
from dotenv import load_dotenv
import psycopg

load_dotenv(encoding="utf-8-sig")

LOG_PATH = "logs/tool_calls.jsonl"

# Arbitrary safety cap, not a real capacity limit - keeps a single JSONL file from growing
# without bound (the "log growth is unbounded" limitation flagged in the Build 4 brief).
# Safe to rotate at all only because this script has already persisted the rollup to
# observability.metrics_history by the time rotation runs - nothing analytically valuable
# is lost when the raw log gets archived.
LOG_ROTATION_THRESHOLD_LINES = 1000


def load_entries():
    with open(LOG_PATH) as f:
        return [json.loads(line) for line in f]


def _connect():
    # Admin role, not appdb_agent_writer - this script is a human-run maintenance job
    # (same pattern as ingest.py/embed_summaries.py), not the agent writing at runtime.
    # agent_scratch stays exclusively "what the agent itself saved."
    return psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=5432,
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def _fetch_previous_run(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT run_at, total_calls, total_questions, avg_turns_per_question, error_rate
            FROM observability.metrics_history
            ORDER BY run_at DESC
            LIMIT 1
        """)
        return cur.fetchone()


def _persist_run(conn, total_calls, total_questions, avg_turns, error_count, error_rate, tool_counts):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO observability.metrics_history
                (total_calls, total_questions, avg_turns_per_question, error_count, error_rate, tool_usage)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        """, (total_calls, total_questions, avg_turns, error_count, error_rate, json.dumps(dict(tool_counts))))
    conn.commit()


def _rotate_log_if_large(entry_count):
    if entry_count < LOG_ROTATION_THRESHOLD_LINES:
        return None
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_path = f"logs/tool_calls.{timestamp}.jsonl"
    os.rename(LOG_PATH, archive_path)
    return archive_path


def main():
    entries = load_entries()

    if not entries:
        print("No log entries found - nothing to report.")
        return

    tool_counts = Counter(e["tool_name"] for e in entries)

    # turn is 1-indexed and increments once per round-trip within one question, so the
    # highest turn value seen for a question_id IS the total turns that question took -
    # no separate "turns used" field needed.
    turns_per_question = {}
    for e in entries:
        qid = e["question_id"]
        turns_per_question[qid] = max(turns_per_question.get(qid, 0), e["turn"])
    avg_turns = sum(turns_per_question.values()) / len(turns_per_question)

    error_count = sum(1 for e in entries if e["error"] is not None)
    error_rate = error_count / len(entries)

    conn = _connect()
    # Fetch the previous run BEFORE inserting this one, or it would just compare against itself.
    previous = _fetch_previous_run(conn)
    _persist_run(conn, len(entries), len(turns_per_question), avg_turns, error_count, error_rate, tool_counts)
    conn.close()

    # Rotation happens after persisting, never before - the rollup above already has this
    # run's full data captured in Postgres regardless of what happens to the raw log next.
    rotated_to = _rotate_log_if_large(len(entries))

    print("\n" + "=" * 70)
    print("METRICS REPORT")
    print("=" * 70)

    print(f"\nTotal tool calls logged: {len(entries)}")
    print(f"Total questions asked:   {len(turns_per_question)}")

    print("\n--- Tool-usage frequency ---")
    for tool_name, count in tool_counts.most_common():
        print(f"  {tool_name}: {count}")

    print("\n--- Average turns per question ---")
    print(f"  {avg_turns:.2f}")

    print("\n--- Error rate ---")
    print(f"  {error_count}/{len(entries)} calls errored ({error_rate:.1%})")

    print("\n--- Trend vs previous run ---")
    if previous is None:
        print("  No previous run recorded - this is the first entry in observability.metrics_history.")
    else:
        prev_run_at, prev_total_calls, prev_total_questions, prev_avg_turns, prev_error_rate = previous

        # Postgres NUMERIC -> Python Decimal -> float can introduce a tiny epsilon even when
        # two values are "the same" (e.g. 2.29 vs 2.2857142857...) - round to display precision
        # FIRST, then normalize: round(-1e-10, 2) is -0.0, and only after rounding does
        # -0.0 == 0 catch it, so checking equality before rounding never works.
        avg_turns_delta = round(avg_turns - float(prev_avg_turns), 2)
        if avg_turns_delta == 0:
            avg_turns_delta = 0.0
        error_rate_delta = round(error_rate - float(prev_error_rate), 4)
        if error_rate_delta == 0:
            error_rate_delta = 0.0

        print(f"  Previous run: {prev_run_at.isoformat()}")
        print(f"  Total calls:      {prev_total_calls} -> {len(entries)} ({len(entries) - prev_total_calls:+d})")
        print(f"  Total questions:  {prev_total_questions} -> {len(turns_per_question)} ({len(turns_per_question) - prev_total_questions:+d})")
        print(f"  Avg turns/question: {float(prev_avg_turns):.2f} -> {avg_turns:.2f} ({avg_turns_delta:+.2f})")
        print(f"  Error rate:       {float(prev_error_rate):.1%} -> {error_rate:.1%} ({error_rate_delta:+.1%})")

    print("\n--- Log rotation ---")
    if rotated_to:
        print(f"  {len(entries)} lines >= {LOG_ROTATION_THRESHOLD_LINES} threshold - archived to {rotated_to}")
        print(f"  logs/tool_calls.jsonl will start fresh on the next tool call.")
    else:
        print(f"  {len(entries)}/{LOG_ROTATION_THRESHOLD_LINES} lines - no rotation needed yet.")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
