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
    # IS NULL makes this idempotent by design from the start, reusing the fix
    # embed_summaries.py needed to have retrofitted in (see that file).
    cur.execute("SELECT chunk_id, chunk_text FROM docs.chunks WHERE embedding IS NULL")
    rows = cur.fetchall()

if not rows:
    print("No chunks need embedding - everything is already up to date.")
    conn.close()
else:
    print(f"Embedding {len(rows)} chunk(s) missing an embedding...")
    texts = [chunk_text for _, chunk_text in rows]
    embeddings = model.encode(texts, show_progress_bar=True)

    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE docs.chunks SET embedding = %s WHERE chunk_id = %s",
            [(embedding, chunk_id) for (chunk_id, _), embedding in zip(rows, embeddings)],
        )
    conn.commit()
    conn.close()

    print(f"Embedded {len(rows)} chunk(s).")
