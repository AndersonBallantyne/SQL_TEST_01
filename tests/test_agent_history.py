import os
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")
# agent.py builds its Anthropic client at import time, which fails immediately with no key
# present at all. CI's regular test job (unlike the gated eval job) never sets one. flatten_history
# is pure and never calls the API, so a harmless dummy value is enough - setdefault leaves a
# real local .env key untouched.

import agent
from agent import flatten_history, MAX_FULL_FIDELITY_ROUNDS, MAX_HISTORY_TOOL_RESULT_CHARS, _cap_tool_results_for_history


def test_empty_history_returns_empty_messages():
    assert flatten_history([]) == []


def test_all_rounds_within_fidelity_window_stay_full():
    rounds = [
        {"user_question": f"question {i}", "answer_text": f"answer {i}",
         "full_messages": [{"role": "user", "content": f"question {i}"},
                            {"role": "assistant", "content": f"answer {i}"}]}
        for i in range(MAX_FULL_FIDELITY_ROUNDS)
    ]
    result = flatten_history(rounds)
    expected = [msg for r in rounds for msg in r["full_messages"]]
    assert result == expected


def test_older_rounds_collapse_to_text_pairs():
    total_rounds = MAX_FULL_FIDELITY_ROUNDS + 2
    rounds = [
        {"user_question": f"question {i}", "answer_text": f"answer {i}",
         "full_messages": [{"role": "user", "content": f"question {i}"},
                            {"role": "assistant", "content": f"answer {i}"},
                            {"role": "assistant", "content": [{"type": "tool_use", "name": "run_sql_query"}]}]}
        for i in range(total_rounds)
    ]
    result = flatten_history(rounds)

    collapsed_expected = []
    for r in rounds[:2]:
        collapsed_expected.append({"role": "user", "content": r["user_question"]})
        collapsed_expected.append({"role": "assistant", "content": r["answer_text"]})
    assert result[:4] == collapsed_expected

    full_expected = [msg for r in rounds[-MAX_FULL_FIDELITY_ROUNDS:] for msg in r["full_messages"]]
    assert result[4:] == full_expected


def _fake_end_turn_response():
    # A single-turn, no-tool-use response is all ask_agent needs to reach its
    # stop_reason != "tool_use" return path - the code path under test here.
    return type("FakeResponse", (), {
        "content": [type("FakeTextBlock", (), {"type": "text", "text": "answer"})()],
        "stop_reason": "end_turn",
        "usage": type("FakeUsage", (), {"input_tokens": 10, "output_tokens": 5})(),
    })()


def test_ask_agent_full_messages_excludes_inherited_history(monkeypatch):
    monkeypatch.setattr(agent.client.messages, "create", lambda **kwargs: _fake_end_turn_response())

    history_rounds = [{
        "user_question": "q1", "answer_text": "a1",
        "full_messages": [{"role": "user", "content": "q1"}, {"role": "assistant", "content": "a1"}],
    }]

    result = agent.ask_agent("q2", history_rounds=history_rounds)

    # ask_agent's returned full_messages must hold only this round's own turns, never the
    # inherited history flatten_history() already prepended - that inherited copy is what
    # made stored history compound every round (live: 6/10/20/40/76/144/274/506/938 messages
    # across 9 real consecutive rounds) once the last MAX_FULL_FIDELITY_ROUNDS rounds' own
    # already-inherited full_messages got spliced into the next round's context in turn.
    assert len(result["full_messages"]) == 2
    assert result["full_messages"][0] == {"role": "user", "content": "q2"}
    assert result["full_messages"][1]["role"] == "assistant"


def test_ask_agent_history_does_not_compound_across_rounds(monkeypatch):
    monkeypatch.setattr(agent.client.messages, "create", lambda **kwargs: _fake_end_turn_response())

    rounds = []
    for i in range(6):
        result = agent.ask_agent(f"question {i}", history_rounds=rounds)
        rounds.append({
            "question_id": result["question_id"],
            "user_question": f"question {i}",
            "answer_text": "answer",
            "full_messages": result["full_messages"],
        })

    # Each round here is a flat 2-message exchange (user + assistant, no tool use), so a
    # correctly-bounded history keeps every round's own stored full_messages at exactly 2 -
    # growth here would mean the compounding bug regressed.
    assert [len(r["full_messages"]) for r in rounds] == [2] * 6


def test_cap_tool_results_truncates_oversized_content_with_a_sentinel():
    big_content = "x" * (MAX_HISTORY_TOOL_RESULT_CHARS + 500)
    messages = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": [{"type": "tool_use", "name": "run_sql_query"}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": big_content}]},
        {"role": "assistant", "content": [{"type": "text", "text": "answer"}]},
    ]

    capped = _cap_tool_results_for_history(messages)

    capped_content = capped[2]["content"][0]["content"]
    assert len(capped_content) < len(big_content)
    assert capped_content.startswith("x" * 100)
    assert f"{len(big_content):,} total chars" in capped_content
    assert "re-run the query" in capped_content
    # Untouched messages (including the tool_use decision itself) pass through unchanged -
    # only a user-role tool_result's own content field is ever modified.
    assert capped[0] == messages[0]
    assert capped[1] == messages[1]
    assert capped[3] == messages[3]


def test_cap_tool_results_leaves_small_content_untouched():
    small_content = "a real, normal-sized tool result"
    messages = [
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": small_content}]},
    ]

    capped = _cap_tool_results_for_history(messages)

    assert capped[0]["content"][0]["content"] == small_content


def test_ask_agent_caps_oversized_tool_results_before_persisting(monkeypatch):
    big_result = "y" * (MAX_HISTORY_TOOL_RESULT_CHARS + 1000)

    call_count = {"n": 0}

    def fake_create(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return type("FakeResponse", (), {
                "content": [type("FakeToolUse", (), {
                    "type": "tool_use", "name": "run_sql_query",
                    "input": {"sql": "SELECT 1"}, "id": "t1",
                })()],
                "stop_reason": "tool_use",
                "usage": type("FakeUsage", (), {"input_tokens": 10, "output_tokens": 5})(),
            })()
        return _fake_end_turn_response()

    monkeypatch.setattr(agent.client.messages, "create", fake_create)
    monkeypatch.setattr(agent, "run_sql_query", lambda sql: big_result)
    monkeypatch.setattr(agent, "log_tool_call", lambda *a, **k: None)

    result = agent.ask_agent("how big is this?")

    tool_result_msg = next(m for m in result["full_messages"] if m["role"] == "user" and isinstance(m["content"], list))
    persisted_content = tool_result_msg["content"][0]["content"]

    # The round's own answer was generated from the real, uncapped big_result (correctness for
    # the live round is untouched) - only what gets persisted for a *future* round to inherit
    # is capped, which this asserts directly on the returned/stored full_messages.
    assert len(persisted_content) < len(big_result)
    assert "history truncated" in persisted_content


def test_ask_agent_flags_a_truncated_answer_instead_of_returning_it_bare(monkeypatch):
    # Reproduces the real 2026-08-08 bug directly: a genuinely in-progress answer hit
    # max_tokens mid-generation and was returned/logged as if it were complete, with nothing
    # anywhere indicating it had been cut off.
    truncated_response = type("FakeResponse", (), {
        "content": [type("FakeTextBlock", (), {"type": "text", "text": "## Total: 14+ bugs\n1. ..."})()],
        "stop_reason": "max_tokens",
        "usage": type("FakeUsage", (), {"input_tokens": 10, "output_tokens": 2048})(),
    })()
    monkeypatch.setattr(agent.client.messages, "create", lambda **kwargs: truncated_response)

    result = agent.ask_agent("how many bugs were found?")

    assert "cut off" in result["answer"]
    assert result["answer"].startswith("## Total: 14+ bugs")
