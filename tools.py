import os
import re
from dotenv import load_dotenv
import psycopg
from psycopg import sql
from datetime import datetime
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer

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
        WHERE table_schema IN ('public', 'clean', 'agent_scratch', 'docs')
        ORDER BY table_name;
    """)

def describe_table(name: str) -> list[dict]:
    return run_sql_query("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema IN ('public', 'clean', 'agent_scratch', 'docs') AND table_name = %s
        ORDER BY ordinal_position;
    """, [name])

_embedding_model = None

def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model

SIMILARITY_DISTANCE_THRESHOLD = 0.63

def search_summaries(query_text: str, limit: int = 5) -> list[dict]:
    model = _get_embedding_model()
    query_embedding = model.encode(query_text)

    conn = psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=5432,
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_READER_USER"],
        password=os.environ["POSTGRES_READER_PASSWORD"],
    )
    register_vector(conn)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT allocation_id, summary, summary_embedding <=> %s AS distance
            FROM clean.allocations
            WHERE summary_embedding <=> %s < %s
            ORDER BY distance
            LIMIT %s
        """, (query_embedding, query_embedding, SIMILARITY_DISTANCE_THRESHOLD, limit))
        rows = cur.fetchall()
    conn.close()

    if not rows:
        return [{"message": f"No sufficiently relevant results for {query_text!r} — nothing scored below the relevance threshold."}]

    return [{"allocation_id": aid, "summary": summary, "distance": round(float(dist), 4)} for aid, summary, dist in rows]


DOCS_SIMILARITY_DISTANCE_THRESHOLD = 0.70  # provisional - not calibrated with Build 3's rigor (40 curated queries); revisit if this proves too loose or too strict

def search_docs(query_text: str, limit: int = 5) -> list[dict]:
    model = _get_embedding_model()
    query_embedding = model.encode(query_text)

    conn = psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=5432,
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_READER_USER"],
        password=os.environ["POSTGRES_READER_PASSWORD"],
    )
    register_vector(conn)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT source_file, chunk_text, embedding <=> %s AS distance
            FROM docs.chunks
            WHERE embedding <=> %s < %s
            ORDER BY distance
            LIMIT %s
        """, (query_embedding, query_embedding, DOCS_SIMILARITY_DISTANCE_THRESHOLD, limit))
        rows = cur.fetchall()
    conn.close()

    if not rows:
        return [{"message": f"No sufficiently relevant documentation found for {query_text!r} — nothing scored below the relevance threshold."}]

    return [{"source_file": sf, "chunk_text": ct, "distance": round(float(d), 4)} for sf, ct, d in rows]



SAFE_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

# Order matters: bool must come before int, since isinstance(True, int) is True in Python.
PG_TYPE_MAP = {
    bool: "BOOLEAN",
    int: "BIGINT",
    float: "DOUBLE PRECISION",
    str: "TEXT",
    datetime: "TIMESTAMP",
}

def _infer_type(value):
    for py_type, pg_type in PG_TYPE_MAP.items():
        if isinstance(value, py_type):
            return pg_type
    raise TypeError(f"Unsupported value type: {type(value)}")

MAX_SCRATCH_TABLES = 50

def save_dataframe(table_name: str, columns: list[str], rows: list[tuple]) -> dict:
    if not SAFE_NAME.match(table_name):
        raise ValueError(f"Invalid table name: {table_name!r}")
    for col in columns:
        if not SAFE_NAME.match(col):
            raise ValueError(f"Invalid column name: {col!r}")
    if not rows:
        raise ValueError("Cannot infer types from an empty result set")

    column_types = [_infer_type(v) for v in rows[0]]

    conn = psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=5432,
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_AGENT_WRITER_USER"],
        password=os.environ["POSTGRES_AGENT_WRITER_PASSWORD"],
    )

    with conn.cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'agent_scratch' AND table_name = %s
            )
        """, [table_name])
        table_already_exists = cur.fetchone()[0]

        if not table_already_exists:
            cur.execute("""
                SELECT count(*) FROM information_schema.tables
                WHERE table_schema = 'agent_scratch'
            """)
            current_count = cur.fetchone()[0]
            if current_count >= MAX_SCRATCH_TABLES:
                conn.close()
                raise RuntimeError(
                    f"agent_scratch already has {current_count} tables "
                    f"(limit {MAX_SCRATCH_TABLES}) - refusing to create another. "
                    f"Clean up existing scratch tables before saving new ones."
                )

        col_defs = sql.SQL(", ").join(
            sql.SQL("{} {}").format(sql.Identifier(col), sql.SQL(pg_type))
            for col, pg_type in zip(columns, column_types)
        )
        create_stmt = sql.SQL("CREATE TABLE IF NOT EXISTS agent_scratch.{} ({})").format(
            sql.Identifier(table_name), col_defs
        )
        cur.execute(create_stmt)

        insert_stmt = sql.SQL("INSERT INTO agent_scratch.{} ({}) VALUES ({})").format(
            sql.Identifier(table_name),
            sql.SQL(", ").join(sql.Identifier(c) for c in columns),
            sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        )
        cur.executemany(insert_stmt, rows)

    conn.commit()
    conn.close()
    print(f"[{datetime.now().isoformat()}] Wrote {len(rows)} rows to agent_scratch.{table_name}")
    return {"schema": "agent_scratch", "table": table_name, "rows_written": len(rows)}



if __name__ == "__main__":
    print(run_sql_query("SELECT id, name, email FROM customers ORDER BY id;"))

    print(list_tables())
    print(describe_table("customers"))
    #print(run_sql_query("DELETE FROM customers;"))
