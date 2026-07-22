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


def test_all_chunks_have_embeddings_with_correct_dimensions():
    conn = _connect_as("POSTGRES_READER_USER", "POSTGRES_READER_PASSWORD")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*), count(embedding)
            FROM docs.chunks
        """)
        total, with_embedding = cur.fetchone()
        cur.execute("""
            SELECT vector_dims(embedding)
            FROM docs.chunks
            LIMIT 1
        """)
        dims = cur.fetchone()[0]
    conn.close()
    assert total == with_embedding
    assert dims == 384


def test_relevant_query_returns_real_results():
    results = tools.search_docs("why does agent_scratch have two separate database roles")
    assert len(results) > 0
    assert "source_file" in results[0]
    assert "distance" in results[0]
    assert results[0]["distance"] < tools.DOCS_SIMILARITY_DISTANCE_THRESHOLD


def test_irrelevant_query_returns_no_match_message():
    results = tools.search_docs("best chocolate chip cookie recipe")
    assert len(results) == 1
    assert "message" in results[0]
    assert "No sufficiently relevant documentation found" in results[0]["message"]


def test_threshold_regression_guard():
    relevant = tools.search_docs("why does agent_scratch have two separate database roles")
    assert relevant[0]["distance"] < tools.DOCS_SIMILARITY_DISTANCE_THRESHOLD

    irrelevant = tools.search_docs("best chocolate chip cookie recipe")
    assert "message" in irrelevant[0]


def test_docs_schema_discoverable_via_list_tables():
    tables = tools.list_tables()
    assert any(t["table_schema"] == "docs" and t["table_name"] == "chunks" for t in tables)
