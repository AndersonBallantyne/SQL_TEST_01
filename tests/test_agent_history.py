import os
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")
# agent.py builds its Anthropic client at import time, which fails immediately with no key
# present at all. CI's regular test job (unlike the gated eval job) never sets one. flatten_history
# is pure and never calls the API, so a harmless dummy value is enough - setdefault leaves a
# real local .env key untouched.

import agent
from agent import flatten_history, MAX_FULL_FIDELITY_ROUNDS


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
