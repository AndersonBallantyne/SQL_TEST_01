import json
import logging_utils

def test_get_verification_found(tmp_path, monkeypatch):
    log_path = tmp_path / "tool_calls.jsonl"
    monkeypatch.setattr(logging_utils, "LOG_PATH", str(log_path))
    entry = {
        "question_id": "abc123", "user_question": "test question",
        "answer_text": "test answer", "supported": True, "reason": "matches evidence",
    }
    with open(log_path, "w") as f:
        f.write(json.dumps(entry) + "\n")
    assert logging_utils.get_verification("abc123") == {"supported": True, "reason": "matches evidence"}

def test_get_verification_not_found(tmp_path, monkeypatch):
    log_path = tmp_path / "tool_calls.jsonl"
    monkeypatch.setattr(logging_utils, "LOG_PATH", str(log_path))
    # A tool_call entry exists for this question_id but no verification entry -
    # simulates the zero-tool-call gate's actual on-disk result.
    entry = {"question_id": "abc123", "tool_name": "list_tables", "input": {}, "latency_ms": 5.0}
    with open(log_path, "w") as f:
        f.write(json.dumps(entry) + "\n")
    assert logging_utils.get_verification("abc123") is None

def test_log_verification_error_writes_a_findable_entry(tmp_path, monkeypatch):
    log_path = tmp_path / "tool_calls.jsonl"
    monkeypatch.setattr(logging_utils, "LOG_PATH", str(log_path))
    logging_utils.log_verification_error("abc123", "how many bugs?", RuntimeError("boom"))

    with open(log_path) as f:
        entry = json.loads(f.readline())
    assert entry["question_id"] == "abc123"
    assert entry["verification_error"] == "boom"

def test_verification_error_entry_never_matches_get_verification(tmp_path, monkeypatch):
    # log_verification_error's entries must stay a distinct shape from log_verification's -
    # keyed on "verification_error", not "supported" - so a real crash can never be
    # misread as a real (if accidentally falsy) verdict by get_verification's own filter.
    log_path = tmp_path / "tool_calls.jsonl"
    monkeypatch.setattr(logging_utils, "LOG_PATH", str(log_path))
    logging_utils.log_verification_error("abc123", "how many bugs?", RuntimeError("boom"))
    assert logging_utils.get_verification("abc123") is None
