import json
import sys

N_QUESTIONS = int(sys.argv[1]) if len(sys.argv) > 1 else 3

with open("logs/tool_calls.jsonl", encoding="utf-8") as f:
    lines = f.readlines()

recent = [json.loads(l) for l in lines[-50:]]
seen = []
for e in recent:
    qid = e.get("question_id")
    if qid not in seen:
        seen.append(qid)

for qid in seen[-N_QUESTIONS:]:
    print(f"=== {qid} ===")
    for e in recent:
        if e.get("question_id") == qid:
            if "tool_name" in e:
                print(f"  turn={e['turn']} tool={e['tool_name']}  q={e['user_question'][:70]!r}")
            else:
                print(f"  [ANSWER] error={e.get('error')}  {e['answer'][:150]!r}")
