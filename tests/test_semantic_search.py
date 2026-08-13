import os
from dotenv import load_dotenv
import psycopg
from pgvector.psycopg import register_vector
import tools

load_dotenv(encoding="utf-8-sig")


def _connect_as(user_env, password_env):
    conn = psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=5432,
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ[user_env],
        password=os.environ[password_env],
    )
    register_vector(conn)
    return conn


def test_hnsw_index_exists_on_summary_embedding():
    conn = _connect_as("POSTGRES_READER_USER", "POSTGRES_READER_PASSWORD")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT am.amname
            FROM pg_index i
            JOIN pg_class c ON c.oid = i.indexrelid
            JOIN pg_am am ON am.oid = c.relam
            WHERE c.relname = 'idx_allocations_summary_embedding_hnsw'
        """)
        row = cur.fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "hnsw"


def test_all_rows_have_embeddings_with_correct_dimensions():
    conn = _connect_as("POSTGRES_READER_USER", "POSTGRES_READER_PASSWORD")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*), count(summary_embedding)
            FROM clean.allocations
        """)
        total, with_embedding = cur.fetchone()
        cur.execute("""
            SELECT vector_dims(summary_embedding)
            FROM clean.allocations
            LIMIT 1
        """)
        dims = cur.fetchone()[0]
    conn.close()
    assert total == with_embedding
    # 384 matches the all-MiniLM-L6-v2 model in use (tools.py) - not an arbitrary number,
    # a mismatch here would mean the column and the model have drifted apart.
    assert dims == 384


def test_relevant_query_returns_real_results():
    results = tools.search_summaries("camera equipment")
    assert len(results) > 0
    assert "allocation_id" in results[0]
    assert "distance" in results[0]
    assert results[0]["distance"] < tools.SIMILARITY_DISTANCE_THRESHOLD


def test_irrelevant_query_returns_no_match_message():
    # "office desk chair" is one of calibrate_threshold.py's curated out-of-domain queries,
    # not a random pick - it's the one confirmed to score well past the threshold.
    results = tools.search_summaries("office desk chair")
    assert len(results) == 1
    assert "message" in results[0]
    assert "No sufficiently relevant results" in results[0]["message"]
