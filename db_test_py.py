import os
from dotenv import load_dotenv
import psycopg

load_dotenv(encoding="utf-8-sig")

# sslmode/gssencmode explicitly disabled from ruling out SSL/GSSAPI negotiation during an
# early connectivity debugging session - the real bug turned out to be an unrelated port
# typo (5443 vs 5432), but these are harmless to leave disabled for local-only dev.
conn = psycopg.connect(
    host="127.0.0.1",
    port=5432,
    dbname=os.environ["POSTGRES_DB"],
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
    sslmode="disable",
    gssencmode="disable",
)
with conn.cursor() as cur:
    cur.execute("SELECT id, name, email FROM customers ORDER BY id;")
    for row in cur.fetchall():
        print(row)

conn.close()        