import os
import sys
from dotenv import load_dotenv
import psycopg
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer

load_dotenv(encoding="utf-8-sig")

query_text = sys.argv[1] if len(sys.argv) > 1 else "camera equipment"

model = SentenceTransformer("all-MiniLM-L6-v2")
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
    # No distance threshold on purpose - this is the standalone proof that raw cosine-distance
    # search works at all, predating any agent wiring. tools.py's search_summaries is the
    # version with SIMILARITY_DISTANCE_THRESHOLD applied.
    cur.execute(
        """
        SELECT allocation_id, summary, summary_embedding <=> %s AS distance
        FROM clean.allocations
        ORDER BY distance
        LIMIT 5
        """,
        (query_embedding,),
    )
    results = cur.fetchall()
conn.close()

print(f"Query: {query_text!r}\n")
for allocation_id, summary, distance in results:
    print(f"[{distance:.4f}] {allocation_id}: {summary[:100]}")
