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


def _clear_todays_log():
    conn = _connect_as("POSTGRES_USER", "POSTGRES_PASSWORD")
    with conn.cursor() as cur:
        cur.execute("DELETE FROM agent_scratch.demo_token_log WHERE logged_at::date = CURRENT_DATE")
    conn.commit()
    conn.close()


def test_todays_usage_is_zero_with_no_rows():
    _clear_todays_log()
    assert tools.get_todays_demo_token_usage() == 0


def test_log_then_read_back_sums_correctly():
    _clear_todays_log()
    try:
        tools.log_demo_token_usage(1000)
        tools.log_demo_token_usage(2500)
        assert tools.get_todays_demo_token_usage() == 3500
    finally:
        _clear_todays_log()


def test_only_todays_rows_are_summed():
    # A row backdated to yesterday must not count toward today's total - the cap is a daily
    # reset, not a running lifetime total.
    _clear_todays_log()
    try:
        tools.log_demo_token_usage(5000)
        conn = _connect_as("POSTGRES_USER", "POSTGRES_PASSWORD")
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE agent_scratch.demo_token_log SET logged_at = now() - interval '1 day' "
                "WHERE logged_at::date = CURRENT_DATE"
            )
        conn.commit()
        conn.close()
        assert tools.get_todays_demo_token_usage() == 0
    finally:
        _clear_todays_log()


def test_demo_token_log_excluded_from_list_tables_and_describe_table():
    tables = tools.list_tables()
    names = [(t["table_schema"], t["table_name"]) for t in tables]
    assert ("agent_scratch", "demo_token_log") not in names

    columns = tools.describe_table("demo_token_log")
    assert columns == []
