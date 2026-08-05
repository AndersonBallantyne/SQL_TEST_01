import os
from dotenv import load_dotenv
import psycopg
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer

load_dotenv(encoding="utf-8-sig")

model = SentenceTransformer("all-MiniLM-L6-v2")

conn = psycopg.connect(
    host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
    port=5432,
    dbname=os.environ["POSTGRES_DB"],
    user=os.environ["POSTGRES_READER_USER"],
    password=os.environ["POSTGRES_READER_PASSWORD"],
)
register_vector(conn)

query_text = input("Question about project history: ")
query_embedding = model.encode(query_text)

with conn.cursor() as cur:
    # Deliberately no distance threshold here, unlike tools.py's search_docs - this is the
    # standalone proof script for inspecting raw top-5 distances directly, which is exactly
    # what surfaced the "top-k always returns something, even when nothing is relevant" gap
    # that led to search_docs/search_summaries needing a cutoff at all.
    cur.execute("""
        SELECT source_file, chunk_text, embedding <=> %s AS distance
        FROM docs.chunks
        ORDER BY distance
        LIMIT 5
    """, (query_embedding,))
    rows = cur.fetchall()

conn.close()

for source_file, chunk_text, distance in rows:
    print(f"\n[{distance:.4f}] {source_file}")
    print(chunk_text[:200])
