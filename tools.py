import os
from dotenv import load_dotenv
import psycopg
from datetime import datetime

load_dotenv(encoding="utf-8-sig")

def run_sql_query(sql: str, params: list | None = None) -> list[dict]:
    if not sql.strip().upper().startswith("SELECT"):
        raise ValueError(f"Only SELECT statments are allowed. Got: {sql!r}")
    print(f"[{datetime.now().isoformat()}] SQL: {sql.strip()}")

    conn = psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=5432,
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_READER_USER"],
        password=os.environ["POSTGRES_READER_PASSWORD"],

    )


    with conn.cursor() as cur:
        cur.execute(sql, params)
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
    conn.close()
    return [dict(zip(columns, row)) for row in rows]

def list_tables() -> list[dict]:
    return run_sql_query("""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema IN ('public', 'clean')
        ORDER BY table_name;
    """)

def describe_table(name: str) -> list[dict]:
    return run_sql_query("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema IN ('public', 'clean') AND table_name = %s
        ORDER BY ordinal_position;
    """, [name])


if __name__ == "__main__":
    print(run_sql_query("SELECT id, name, email FROM customers ORDER BY id;"))

    print(list_tables())
    print(describe_table("customers"))
    #print(run_sql_query("DELETE FROM customers;"))
