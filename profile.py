import os
from dotenv import load_dotenv
import psycopg
import pandas as pd

load_dotenv(encoding="utf-8-sig")

conn = psycopg.connect(
    host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
    port=5432,
    dbname=os.environ["POSTGRES_DB"],
    user=os.environ["POSTGRES_READER_USER"],
    password=os.environ["POSTGRES_READER_PASSWORD"],
)

with conn.cursor() as cur:
    cur.execute("SELECT * FROM raw.allocations")
    columns = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
conn.close()

df = pd.DataFrame(rows, columns=columns)

print("Row count:", len(df))

print("\n--- patron_department: blank rate + distinct values (repr shows hidden whitespace) ---")
print("Blank count:", (df["patron_department"] == "").sum())
print(sorted(repr(v) for v in df["patron_department"].unique()))

print("\n--- patron_email: distinct domains ---")
print(df["patron_email"].value_counts(dropna=False))

print("\n--- date format consistency: actual_start / scheduled_end / actual_end ---")
for col in ["actual_start", "scheduled_end", "actual_end"]:
    parsed = pd.to_datetime(df[col], format="%m/%d/%Y %I:%M %p", errors="coerce")
    print(f"{col}: {parsed.isna().sum()} rows failed to parse with format MM/DD/YYYY H:MM AM/PM")

print("\n--- duration sanity check ---")
starts = pd.to_datetime(df["actual_start"], format="%m/%d/%Y %I:%M %p", errors="coerce")
ends = pd.to_datetime(df["actual_end"], format="%m/%d/%Y %I:%M %p", errors="coerce")
computed_seconds = (ends - starts).dt.total_seconds()
mismatch = computed_seconds.astype("Int64") != df["duration"].astype("int64")
print("Rows where computed (actual_end - actual_start) != stored duration:", mismatch.sum())

print("\n--- renewal_count / resource_count: non-numeric rows ---")
print("renewal_count non-digit rows:", (~df["renewal_count"].str.fullmatch(r"\d+")).sum())
print("resource_count non-digit rows:", (~df["resource_count"].str.fullmatch(r"\d+")).sum())
