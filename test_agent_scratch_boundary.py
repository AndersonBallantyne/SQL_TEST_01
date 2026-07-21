import os
import pytest
from dotenv import load_dotenv
import psycopg

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
