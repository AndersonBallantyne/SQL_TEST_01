import os
import random
from dotenv import load_dotenv
import psycopg
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer

load_dotenv(encoding="utf-8-sig")

random.seed(42)

model = SentenceTransformer("all-MiniLM-L6-v2")

conn = psycopg.connect(
    host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
    port=5432,
    dbname=os.environ["POSTGRES_DB"],
    user=os.environ["POSTGRES_READER_USER"],
    password=os.environ["POSTGRES_READER_PASSWORD"],
)
register_vector(conn)

# --- In-domain: real summaries already in the corpus, nearest neighbor excluding self ---
with conn.cursor() as cur:
    cur.execute("SELECT allocation_id, summary FROM clean.allocations WHERE summary IS NOT NULL")
    all_rows = cur.fetchall()

in_domain_queries = [
    "camera equipment", "video tripod", "audio recording gear", "lighting kit",
    "memory card", "laptop charger", "camera lens", "microphone", "HDMI cable",
    "battery charger", "tripod head", "SD card reader", "camera bag",
    "USB adapter", "video slider", "LED light panel", "boom pole",
    "camera stabilizer", "power supply", "storage case",
]

in_domain_distances = []
with conn.cursor() as cur:
    for query in in_domain_queries:
        embedding = model.encode(query)
        cur.execute("""
            SELECT summary_embedding <=> %s AS distance
            FROM clean.allocations
            ORDER BY distance
            LIMIT 1
        """, (embedding,))
        in_domain_distances.append(float(cur.fetchone()[0]))

# --- Out-of-domain: curated queries for things this corpus has none of ---
out_of_domain_queries = [
    "office desk chair", "kitchen blender", "garden shovel", "running shoes",
    "bicycle helmet", "bed sheets", "coffee maker", "wine glass", "yoga mat",
    "umbrella stroller", "dog leash", "board game", "power drill", "paint roller",
    "hiking backpack", "swimming goggles", "electric toothbrush", "vacuum cleaner",
    "sofa cushion", "winter jacket",
]

out_of_domain_distances = []
with conn.cursor() as cur:
    for query in out_of_domain_queries:
        embedding = model.encode(query)
        cur.execute("""
            SELECT summary_embedding <=> %s AS distance
            FROM clean.allocations
            ORDER BY distance
            LIMIT 1
        """, (embedding,))
        out_of_domain_distances.append(float(cur.fetchone()[0]))

conn.close()

def stats(label, values):
    values_sorted = sorted(values)
    n = len(values_sorted)
    mean = sum(values_sorted) / n
    median = values_sorted[n // 2]
    print(f"{label}: n={n} min={min(values_sorted):.4f} max={max(values_sorted):.4f} mean={mean:.4f} median={median:.4f}")

print("\n--- In-domain (real corpus summaries) ---")
stats("in-domain", in_domain_distances)

print("\n--- Out-of-domain (curated unrelated queries) ---")
stats("out-of-domain", out_of_domain_distances)

gap_low, gap_high = max(in_domain_distances), min(out_of_domain_distances)
print(f"\nIn-domain max = {gap_low:.4f}, out-of-domain min = {gap_high:.4f}")
if gap_low < gap_high:
    print(f"Clean separation - midpoint threshold ~{(gap_low + gap_high) / 2:.4f}")
else:
    print("Overlap between groups - no clean separation; threshold involves a real tradeoff.")

# This run's midpoint is where tools.py's SIMILARITY_DISTANCE_THRESHOLD (0.63) came from -
# it's the one threshold in this project actually backed by curated in-/out-of-domain
# measurement, not a provisional guess (contrast DOCS_SIMILARITY_DISTANCE_THRESHOLD there).
