import csv
import os
from dotenv import load_dotenv
import psycopg

load_dotenv(encoding="utf-8-sig")

# data/ALLOCATION-synthesized.csv is the project's official dataset as of Build 5 - real
# dates/durations/renewal/resource counts preserved row-for-row from the original real export,
# but allocation_id, department, email domain, and every equipment description synthesized
# (see synthesize_dataset.py) so the real institution's real operational data never needs to
# leave this machine at all, in either the real or the fixture path - there's only one dataset
# now, and it's already safe to commit. Still overridable for one-off local experiments.
CSV_PATH = os.environ.get("ALLOCATIONS_CSV_PATH", "data/ALLOCATION-synthesized.csv")

conn = psycopg.connect(
    host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
    port=5432,
    dbname=os.environ["POSTGRES_DB"],
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
)

with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
    # csv.DictReader, not pandas, is deliberate here even though pandas is used elsewhere in
    # this project (transform.py, profile_raw_data.py) - this is the raw ingestion layer, and
    # the whole point is loading source data with nothing silently type-coerced along the way.
    reader = csv.DictReader(f)
    rows = [
        (
            row["Allocation"],
            row["Patron Department"],
            row["Patron Email"],
            row["Renewal Count"],
            row["Actual Start"],
            row["Scheduled End"],
            row["Actual End"],
            row["Duration"],
            row["Resource Count"],
            row["Summary"],
        )
        for row in reader
    ]

with conn.cursor() as cur:
    cur.executemany(
        """
        INSERT INTO raw.allocations (
            allocation_id, patron_department, patron_email, renewal_count,
            actual_start, scheduled_end, actual_end, duration,
            resource_count, summary
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        rows,
    )
conn.commit()
conn.close()

print(f"Loaded {len(rows)} rows into raw.allocations")

