import os
from dotenv import load_dotenv
import psycopg
import tools

load_dotenv(encoding="utf-8-sig")


def _connect_as(user_env, password_env):
    return psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=5432,
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ[user_env],
        password=os.environ[password_env],
    )


def _cleanup(question_ids):
    conn = _connect_as("POSTGRES_AGENT_WRITER_USER", "POSTGRES_AGENT_WRITER_PASSWORD")
    with conn.cursor() as cur:
        cur.executemany(
            "DELETE FROM agent_scratch.chat_rounds WHERE question_id = %s",
            [(qid,) for qid in question_ids],
        )
    conn.commit()
    conn.close()


def test_save_and_load_chat_round_round_trip():
    qid = "pytest_roundtrip_001"
    full_messages = [
        {"role": "user", "content": "test question"},
        {"role": "assistant", "content": [{"type": "text", "text": "test answer"}]},
    ]
    try:
        tools.save_chat_round(qid, "test question", "test answer", full_messages)

        rounds = tools.load_chat_rounds()
        match = [r for r in rounds if r["question_id"] == qid]
        assert len(match) == 1
        assert match[0]["user_question"] == "test question"
        assert match[0]["answer_text"] == "test answer"
        # Confirms the model_dump()-via-json.dumps(default=...) hook and psycopg's native
        # jsonb round-trip both preserve structure exactly, including a nested list of dicts.
        assert match[0]["full_messages"] == full_messages
    finally:
        _cleanup([qid])


def test_chat_rounds_not_discoverable_via_list_tables_or_describe_table():
    tables = tools.list_tables()
    assert not any(t.get("table_name") == "chat_rounds" for t in tables)
    assert tools.describe_table("chat_rounds") == []


def test_chat_rounds_cap_trims_oldest_rows(monkeypatch):
    # monkeypatch to a small cap to hit the boundary without writing 200 real rows.
    monkeypatch.setattr(tools, "MAX_CHAT_ROUNDS", 3)

    question_ids = [f"pytest_cap_test_{i:03d}" for i in range(5)]
    try:
        for qid in question_ids:
            tools.save_chat_round(qid, f"question {qid}", f"answer {qid}", [])

        rounds = tools.load_chat_rounds()
        remaining_ids = {r["question_id"] for r in rounds}

        # Only the last 3 of the 5 saved rounds should survive the trim - the cap applies
        # globally to the table, not just to this test's own rows, so this only asserts on
        # the test's own question_ids rather than the table's total row count.
        surviving_test_rows = [qid for qid in question_ids if qid in remaining_ids]
        assert surviving_test_rows == question_ids[-3:], (
            f"expected only the 3 most recent test rows to survive, got {surviving_test_rows}"
        )
        assert question_ids[0] not in remaining_ids
        assert question_ids[1] not in remaining_ids
    finally:
        _cleanup(question_ids)
