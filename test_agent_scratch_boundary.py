import os
import pytest
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


def test_writer_has_no_elevated_privileges():
    conn = _connect_as("POSTGRES_USER", "POSTGRES_PASSWORD")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT rolsuper, rolcreaterole, rolcreatedb
            FROM pg_roles WHERE rolname = 'appdb_agent_writer'
        """)
        rolsuper, rolcreaterole, rolcreatedb = cur.fetchone()
    conn.close()
    assert not rolsuper
    assert not rolcreaterole
    assert not rolcreatedb


def test_writer_blocked_from_clean_schema():
    conn = _connect_as("POSTGRES_AGENT_WRITER_USER", "POSTGRES_AGENT_WRITER_PASSWORD")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with conn.cursor() as cur:
            cur.execute("CREATE TABLE clean.pytest_boundary_test (x int)")
    conn.close()


def test_writer_blocked_from_public_schema():
    conn = _connect_as("POSTGRES_AGENT_WRITER_USER", "POSTGRES_AGENT_WRITER_PASSWORD")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with conn.cursor() as cur:
            cur.execute("CREATE TABLE public.pytest_boundary_test (x int)")
    conn.close()


def test_writer_can_create_and_reader_can_see_it_in_agent_scratch():
    writer_conn = _connect_as("POSTGRES_AGENT_WRITER_USER", "POSTGRES_AGENT_WRITER_PASSWORD")
    with writer_conn.cursor() as cur:
        cur.execute("CREATE TABLE agent_scratch.pytest_boundary_test (note text)")
        cur.execute("INSERT INTO agent_scratch.pytest_boundary_test (note) VALUES ('ok')")
    writer_conn.commit()

    reader_conn = _connect_as("POSTGRES_READER_USER", "POSTGRES_READER_PASSWORD")
    with reader_conn.cursor() as cur:
        cur.execute("SELECT note FROM agent_scratch.pytest_boundary_test")
        row = cur.fetchone()
    reader_conn.close()
    assert row[0] == "ok"

    with writer_conn.cursor() as cur:
        cur.execute("DROP TABLE agent_scratch.pytest_boundary_test")
    writer_conn.commit()
    writer_conn.close()


def test_scratch_table_cap_blocks_new_tables_but_not_existing_ones(monkeypatch):
    # monkeypatch, not 50 real tables, to hit the cap's exact boundary - auto-restored after
    # this test, so it never actually costs the real limit's protection elsewhere.
    monkeypatch.setattr(tools, "MAX_SCRATCH_TABLES", 0)

    with pytest.raises(RuntimeError):
        tools.save_dataframe("pytest_cap_test_new_table", ["x"], [(1,)])

    # An existing table should still accept new rows even "at" the cap -
    # the cap only ever blocks creating a brand-new table.
    # Reuses the real domain_avg_duration table (from Build 2.5), not a fresh pytest-only
    # one - a new table name here would hit the "doesn't exist yet" branch and test the
    # wrong path entirely. Only the inserted test row gets cleaned up below, not the table.
    result = tools.save_dataframe(
        "domain_avg_duration", ["patron_email_domain", "avg_duration_hours"], [("@pytest.test", 0.0)]
    )
    assert result["rows_written"] == 1

    conn = _connect_as("POSTGRES_AGENT_WRITER_USER", "POSTGRES_AGENT_WRITER_PASSWORD")
    with conn.cursor() as cur:
        cur.execute("DELETE FROM agent_scratch.domain_avg_duration WHERE patron_email_domain = '@pytest.test'")
    conn.commit()
    conn.close()
