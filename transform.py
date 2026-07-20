import os
from datetime import datetime
from dotenv import load_dotenv
import psycopg

load_dotenv(encoding="utf-8-sig")

conn = psycopg.connect(
    host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
    port=5432,
    dbname=os.environ["POSTGRES_DB"],
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
)

DATE_FORMAT = "%m/%d/%Y %I:%M %p"

with conn.cursor() as cur:
    cur.execute("SELECT * FROM raw.allocations")
    columns = [desc[0] for desc in cur.description]
    raw_rows = cur.fetchall()

rows = []
for row in raw_rows:
    record = dict(zip(columns, row))
    rows.append((
        record["allocation_id"],
        record["patron_department"] or None,
        record["patron_email"],
        int(record["renewal_count"]),
        datetime.strptime(record["actual_start"], DATE_FORMAT),
        datetime.strptime(record["scheduled_end"], DATE_FORMAT),
        datetime.strptime(record["actual_end"], DATE_FORMAT),
        int(record["resource_count"]),
        record["summary"],
    ))

with conn.cursor() as cur:
    cur.executemany(
        """
        INSERT INTO clean.allocations (
            allocation_id, patron_department, patron_email_domain, renewal_count,
            actual_start, scheduled_end, actual_end,
            resource_count, summary
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        rows,
    )
conn.commit()
conn.close()

print(f"Loaded {len(rows)} rows into clean.allocations")
