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
