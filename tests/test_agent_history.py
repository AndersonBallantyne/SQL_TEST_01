import os
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")
# agent.py builds its Anthropic client at import time, which fails immediately with no key
# present at all. CI's regular test job (unlike the gated eval job) never sets one. flatten_history
# is pure and never calls the API, so a harmless dummy value is enough - setdefault leaves a
# real local .env key untouched.

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
