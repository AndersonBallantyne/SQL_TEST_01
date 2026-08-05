import json
import os
from datetime import datetime

LOG_PATH = "logs/tool_calls.jsonl"

def log_tool_call(tool_name, input_data, output_data, latency_ms, turn, question_id, user_question=None, error=None):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        # Groups a question's turns back together - "turn" alone resets to 1 for every
        # ask_agent() call, so it can't disambiguate two conversations logging at once.
        "question_id": question_id,
        # The natural-language question itself was never logged before this fix (2026-07-29) -
        # every entry recorded what tool ran, never what the user actually asked, discovered
        # only when trying to hand back the exact question that had triggered a prior bug.
        "user_question": user_question,
        "turn": turn,
        "tool_name": tool_name,
        "input": input_data,
        "output": output_data if error is None else None,
        "error": error,
        "latency_ms": round(latency_ms, 2),
    }
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")

def get_tool_calls(question_id, include_output=False):
    # Reuses the Phase 1 log as the source of truth (same pattern as run_eval.py) instead of
    # threading a parallel tool-call tracker through app.py - filters to entries carrying
    # "tool_name" so log_final_answer's differently-shaped entries are skipped automatically.
    # include_output defaults False so the existing Phase 4 UI callers/tests are unaffected -
    # verify_answer.py (Build 7) is the only caller that needs the raw output/question text.
    if not os.path.exists(LOG_PATH):
        return []
    calls = []
    with open(LOG_PATH) as f:
        for line in f:
            entry = json.loads(line)
            if entry.get("question_id") == question_id and "tool_name" in entry:
                call = {
                    "tool_name": entry["tool_name"],
                    "input": entry["input"],
                    "latency_ms": entry["latency_ms"],
                }
                if include_output:
                    call["output"] = entry["output"]
                    call["user_question"] = entry["user_question"]
                calls.append(call)
    return calls

def get_verification(question_id):
    if not os.path.exists(LOG_PATH):
        return None

    with open(LOG_PATH) as f:
        for line in f:
            entry = json.loads(line)
            if entry.get("question_id") == question_id and "supported" in entry:
                return {"supported": entry["supported"], "reason": entry["reason"]}
    return None


def get_final_answer(question_id):
    # Reuses the Phase 1 log as the source of truth (same pattern as run_eval.py) instead of
    # threading a parallel tool-call tracker through app.py - filters to entries carrying
    # "answer" so log_final_answer's differently-shaped entries are skipped automatically.
    if not os.path.exists(LOG_PATH):
        return None

    with open(LOG_PATH) as f:
        for line in f:
            entry = json.loads(line)
            if entry.get("question_id") == question_id and "answer" in entry:
                return entry["answer"]
    return None

def log_final_answer(question_id, user_question, answer, error=None):
    # A distinct event shape from log_tool_call's entries (no tool_name/turn/input/output/
    # latency_ms) - the model's final answer isn't a tool call, it's what ask_agent() returns
    # to the caller. Added 2026-07-29 after discovering the log had no record of it at all,
    # while verifying Build 6 Phase 2's boundary test against real browser Q&A.
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "question_id": question_id,
        "user_question": user_question,
        "answer": answer,
        "error": error,
    }
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")
def log_verification(question_id, user_question, answer, supported, reason):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "question_id": question_id,
        "user_question": user_question,
        "answer_text": answer,
        "supported": supported,
        "reason": reason,
    }
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")
