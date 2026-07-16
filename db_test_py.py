import os
from dotenv import load_dotenv
import psycopg

load_dotenv(encoding="utf-8-sig")

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