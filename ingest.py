import csv
import os
from dotenv import load_dotenv
import psycopg

load_dotenv(encoding="utf-8-sig")

# Overridable so CI can point this at the small masked ci_fixture/ CSV instead - the real
# export never leaves this machine, so a CI runner has no way to reach the hardcoded default.
CSV_PATH = os.environ.get(
    "ALLOCATIONS_CSV_PATH",
    r"C:\IMAGEBANK_2023\DOCKER_SQL\EMEC_AGENT_BUILD\ALLOCATION-export-Oct_2024-2025.csv",
)

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

