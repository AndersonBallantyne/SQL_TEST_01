import json
from collections import Counter

LOG_PATH = "logs/tool_calls.jsonl"


def load_entries():
    with open(LOG_PATH) as f:
        return [json.loads(line) for line in f]


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

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
