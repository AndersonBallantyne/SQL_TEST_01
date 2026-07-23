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
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
)
register_vector(conn)

with conn.cursor() as cur:
    # IS NULL makes this idempotent/incremental - originally re-embedded all 1535 rows on
    # every run regardless of what changed. Verified live by nulling 2 real rows and
    # confirming only those 2 got reprocessed, not the full table.
    cur.execute("SELECT allocation_id, summary FROM clean.allocations WHERE summary_embedding IS NULL")
    rows = cur.fetchall()

if not rows:
    print("No rows need embedding - everything is already up to date.")
    conn.close()
else:
    print(f"Embedding {len(rows)} row(s) missing a summary_embedding...")
    texts = [summary if summary else "" for _, summary in rows]
    embeddings = model.encode(texts, show_progress_bar=True)

    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE clean.allocations SET summary_embedding = %s WHERE allocation_id = %s",
            [(embedding, allocation_id) for (allocation_id, _), embedding in zip(rows, embeddings)],
        )
    conn.commit()
    conn.close()

    print(f"Embedded {len(rows)} row(s).")
