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


def _backdate(table_name, days_ago):
    # Uses the superuser connection, not appdb_agent_writer - UPDATE on table_metadata is
    # deliberately not granted to the writer role (it only ever needs INSERT, on creation, and
    # DELETE, on cleanup), so backdating a row to simulate the passage of time is a test-only
    # capability, not something production code should be able to do.
    conn = _connect_as("POSTGRES_USER", "POSTGRES_PASSWORD")
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE agent_scratch.table_metadata SET created_at = now() - (%s || ' days')::interval "
            "WHERE table_name = %s",
            [days_ago, table_name],
        )
    conn.commit()
    conn.close()


def _cleanup(*table_names):
    conn = _connect_as("POSTGRES_AGENT_WRITER_USER", "POSTGRES_AGENT_WRITER_PASSWORD")
    with conn.cursor() as cur:
        for name in table_names:
            cur.execute(f"DROP TABLE IF EXISTS agent_scratch.{name}")
            cur.execute("DELETE FROM agent_scratch.table_metadata WHERE table_name = %s", [name])
    conn.commit()
    conn.close()


def test_new_table_gets_a_metadata_row():
    table_name = "pytest_cleanup_fresh"
    _cleanup(table_name)
    try:
        tools.save_dataframe(table_name, ["x"], [(1,)])
        conn = _connect_as("POSTGRES_READER_USER", "POSTGRES_READER_PASSWORD")
        with conn.cursor() as cur:
            cur.execute("SELECT created_at FROM agent_scratch.table_metadata WHERE table_name = %s", [table_name])
            row = cur.fetchone()
        conn.close()
        assert row is not None
    finally:
        _cleanup(table_name)


def test_fresh_table_is_not_reported_as_stale():
    table_name = "pytest_cleanup_fresh2"
    _cleanup(table_name)
    try:
        tools.save_dataframe(table_name, ["x"], [(1,)])
        stale = tools.list_stale_scratch_tables(mention_after_days=7)
        assert table_name not in [t["table_name"] for t in stale]
    finally:
        _cleanup(table_name)


def test_table_10_days_old_is_worth_mentioning_but_not_eligible():
    table_name = "pytest_cleanup_10d"
    _cleanup(table_name)
    try:
        tools.save_dataframe(table_name, ["x"], [(1,)])
        _backdate(table_name, 10)
        stale = tools.list_stale_scratch_tables(mention_after_days=7, delete_eligible_after_days=30)
        entry = next(t for t in stale if t["table_name"] == table_name)
        assert entry["eligible_for_deletion"] is False
        assert entry["age_days"] >= 10
    finally:
        _cleanup(table_name)


def test_table_35_days_old_is_eligible_for_deletion():
    table_name = "pytest_cleanup_35d"
    _cleanup(table_name)
    try:
        tools.save_dataframe(table_name, ["x"], [(1,)])
        _backdate(table_name, 35)
        stale = tools.list_stale_scratch_tables(mention_after_days=7, delete_eligible_after_days=30)
        entry = next(t for t in stale if t["table_name"] == table_name)
        assert entry["eligible_for_deletion"] is True
    finally:
        _cleanup(table_name)


def test_delete_refuses_a_table_that_is_not_yet_eligible():
    table_name = "pytest_cleanup_refuse"
    _cleanup(table_name)
    try:
        tools.save_dataframe(table_name, ["x"], [(1,)])
        _backdate(table_name, 10)
        result = tools.delete_scratch_tables([table_name])
        assert result["deleted"] == []
        assert result["skipped"][0]["table_name"] == table_name

        conn = _connect_as("POSTGRES_READER_USER", "POSTGRES_READER_PASSWORD")
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('agent_scratch.pytest_cleanup_refuse')")
            still_exists = cur.fetchone()[0] is not None
        conn.close()
        assert still_exists
    finally:
        _cleanup(table_name)


def test_delete_removes_an_eligible_table_and_its_metadata():
    table_name = "pytest_cleanup_delete"
    _cleanup(table_name)
    try:
        tools.save_dataframe(table_name, ["x"], [(1,)])
        _backdate(table_name, 45)
        result = tools.delete_scratch_tables([table_name])
        assert result["deleted"] == [table_name]

        conn = _connect_as("POSTGRES_READER_USER", "POSTGRES_READER_PASSWORD")
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('agent_scratch.pytest_cleanup_delete')")
            table_gone = cur.fetchone()[0] is None
            cur.execute("SELECT * FROM agent_scratch.table_metadata WHERE table_name = %s", [table_name])
            metadata_gone = cur.fetchone() is None
        conn.close()
        assert table_gone
        assert metadata_gone
    finally:
        _cleanup(table_name)


def test_delete_rejects_an_invalid_table_name():
    result = tools.delete_scratch_tables(["not a safe name; DROP TABLE x"])
    assert result["deleted"] == []
    assert "invalid" in result["skipped"][0]["reason"]


def test_delete_refuses_protected_system_tables():
    result = tools.delete_scratch_tables(["chat_rounds", "table_metadata"])
    assert result["deleted"] == []
    assert len(result["skipped"]) == 2
    assert all("protected" in s["reason"] for s in result["skipped"])


def test_delete_with_require_eligibility_false_deletes_a_fresh_table():
    # The "delete any table now" UI path (app.py) - a human explicitly picking a table by
    # name is a different trust context than the agent or an automated caller, which is what
    # the eligibility gate was actually built to stop.
    table_name = "pytest_cleanup_immediate"
    _cleanup(table_name)
    try:
        tools.save_dataframe(table_name, ["x"], [(1,)])  # 0 days old - would normally be refused
        result = tools.delete_scratch_tables([table_name], require_eligibility=False)
        assert result["deleted"] == [table_name]
        assert result["skipped"] == []
    finally:
        _cleanup(table_name)


def test_delete_with_require_eligibility_false_still_rejects_invalid_and_protected_names():
    # SAFE_NAME and the protected-name check are never skippable, in either mode - bypassing
    # the age gate was a deliberate, scoped decision, not a general "trust the caller" switch.
    result = tools.delete_scratch_tables(
        ["not a safe name", "chat_rounds", "table_metadata"], require_eligibility=False
    )
    assert result["deleted"] == []
    assert len(result["skipped"]) == 3


def test_list_all_scratch_tables_includes_a_fresh_table_and_excludes_system_tables():
    table_name = "pytest_cleanup_list_all"
    _cleanup(table_name)
    try:
        tools.save_dataframe(table_name, ["x"], [(1,)])
        names = [t["table_name"] for t in tools.list_all_scratch_tables()]
        assert table_name in names
        assert "chat_rounds" not in names
        assert "table_metadata" not in names
    finally:
        _cleanup(table_name)


def test_table_metadata_excluded_from_list_tables_and_describe_table():
    tables = tools.list_tables()
    names = [(t["table_schema"], t["table_name"]) for t in tables]
    assert ("agent_scratch", "table_metadata") not in names

    columns = tools.describe_table("table_metadata")
    assert columns == []
