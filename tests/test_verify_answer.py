import os
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")
# verify_answer.py builds its Anthropic client at import time - see test_agent_history.py's
# identical comment for why a harmless dummy key is needed for CI's non-eval test job.

import pytest
import verify_answer


def _fake_response(stop_reason, tool_input):
    block = type("FakeToolUse", (), {"type": "tool_use", "name": "report_verdict", "input": tool_input})()
    return type("FakeResponse", (), {"content": [block], "stop_reason": stop_reason})()


def test_verify_answer_normal_case_unaffected(monkeypatch):
    monkeypatch.setattr(
        verify_answer.client.messages, "create",
        lambda **kwargs: _fake_response("end_turn", {"supported": True, "reason": "matches the evidence"}),
    )
    supported, reason = verify_answer.verify_answer("q", "a", [])
    assert supported is True
    assert reason == "matches the evidence"


def test_verify_answer_falls_back_when_reason_truncated_away(monkeypatch):
    # Reproduces the real 2026-08-08 crash directly: report_verdict's JSON got cut off by
    # max_tokens after "supported" but before "reason" was ever written.
    monkeypatch.setattr(
        verify_answer.client.messages, "create",
        lambda **kwargs: _fake_response("max_tokens", {"supported": False}),
    )
    supported, reason = verify_answer.verify_answer("q", "a", [])
    assert supported is False
    assert "cut off" in reason


def test_verify_answer_raises_when_supported_itself_is_missing(monkeypatch):
    # A worse truncation than the reproduced case - nothing usable came back at all. This
    # should still fail loudly (agent.py's own try/except is the intended safety net for this,
    # not a silent fallback verdict that could misrepresent what was actually checked).
    monkeypatch.setattr(
        verify_answer.client.messages, "create",
        lambda **kwargs: _fake_response("max_tokens", {}),
    )
    with pytest.raises(RuntimeError):
        verify_answer.verify_answer("q", "a", [])


def test_verify_answer_raises_when_no_tool_use_block_returned(monkeypatch):
    empty_response = type("FakeResponse", (), {"content": [], "stop_reason": "end_turn"})()
    monkeypatch.setattr(verify_answer.client.messages, "create", lambda **kwargs: empty_response)
    with pytest.raises(RuntimeError):
        verify_answer.verify_answer("q", "a", [])
