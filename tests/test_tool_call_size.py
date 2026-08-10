import json
import logging_utils

def test_log_tool_call_records_result_size(tmp_path, monkeypatch):
    log_path = tmp_path / "tool_calls.jsonl"
    monkeypatch.setattr(logging_utils, "LOG_PATH", str(log_path))
    result = [{"table_name": "x"}, {"table_name": "y"}]
    logging_utils.log_tool_call("list_tables", {}, result, 5.0, 1, "abc123")

    with open(log_path) as f:
        entry = json.loads(f.readline())
    expected_chars = len(str(result))
    assert entry["result_chars"] == expected_chars
    assert entry["approx_tokens"] == round(expected_chars / 4)

def test_log_tool_call_zero_size_on_error(tmp_path, monkeypatch):
    log_path = tmp_path / "tool_calls.jsonl"
    monkeypatch.setattr(logging_utils, "LOG_PATH", str(log_path))
    # Matches how agent.py actually calls this on failure - output_data is None, not omitted.
    logging_utils.log_tool_call("run_sql_query", {"sql": "bad"}, None, 2.0, 1, "abc123", error="syntax error")

    with open(log_path) as f:
        entry = json.loads(f.readline())
    assert entry["result_chars"] == 0
    assert entry["approx_tokens"] == 0

def test_get_tool_calls_surfaces_size_fields(tmp_path, monkeypatch):
    log_path = tmp_path / "tool_calls.jsonl"
    monkeypatch.setattr(logging_utils, "LOG_PATH", str(log_path))
    logging_utils.log_tool_call("search_docs", {"query_text": "x"}, "a" * 400, 10.0, 1, "abc123")

    calls = logging_utils.get_tool_calls("abc123")
    assert len(calls) == 1
    assert calls[0]["result_chars"] == 400
    assert calls[0]["approx_tokens"] == 100

def test_get_tool_calls_defaults_size_fields_for_old_log_lines(tmp_path, monkeypatch):
    # Entries logged before this feature existed have no result_chars/approx_tokens at all -
    # reloading a persisted chat round from before this change must not crash.
    log_path = tmp_path / "tool_calls.jsonl"
    monkeypatch.setattr(logging_utils, "LOG_PATH", str(log_path))
    old_entry = {"question_id": "abc123", "tool_name": "list_tables", "input": {}, "latency_ms": 5.0}
    with open(log_path, "w") as f:
        f.write(json.dumps(old_entry) + "\n")

    calls = logging_utils.get_tool_calls("abc123")
    assert calls[0]["result_chars"] == 0
    assert calls[0]["approx_tokens"] == 0
