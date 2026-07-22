import json
import os
from datetime import datetime

LOG_PATH = "logs/tool_calls.jsonl"

def log_tool_call(tool_name, input_data, output_data, latency_ms, turn, error=None):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "turn": turn,
        "tool_name": tool_name,
        "input": input_data,
        "output": output_data if error is None else None,
        "error": error,
        "latency_ms": round(latency_ms, 2),
    }
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")
