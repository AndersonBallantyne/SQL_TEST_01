import os
from dotenv import load_dotenv
import psycopg
import pandas as pd
import pandera.pandas as pa

load_dotenv(encoding="utf-8-sig")


def _query(sql):
    conn = psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=5432,
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_READER_USER"],
        password=os.environ["POSTGRES_READER_PASSWORD"],
    )
    with conn.cursor() as cur:
        cur.execute(sql)
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
    conn.close()
    return pd.DataFrame(rows, columns=columns)


CLEAN_SCHEMA = pa.DataFrameSchema({
    "allocation_id": pa.Column(str, unique=True, nullable=False),
    "patron_department": pa.Column(str, nullable=True),
    "patron_email_domain": pa.Column(str, nullable=False),
    "renewal_count": pa.Column(int, pa.Check.ge(0), nullable=False),
    "resource_count": pa.Column(int, pa.Check.ge(0), nullable=False),
    "duration_seconds": pa.Column(int, pa.Check.ge(0), nullable=False),
})


def test_raw_row_count():
    # 1535 is the real source CSV's row count locally. CI ingests a small masked fixture
    # instead (ci_fixture/, see make_ci_fixture.py) and overrides this via
    # EXPECTED_RAW_ROW_COUNT - either way, this guards against ingest.py silently dropping or
    # duplicating rows on a re-run against whatever the current source actually contains.
    expected = int(os.environ.get("EXPECTED_RAW_ROW_COUNT", "1535"))
    raw = _query("SELECT * FROM raw.allocations")
    assert len(raw) == expected


def test_clean_row_count_matches_raw():
    raw = _query("SELECT COUNT(*) AS n FROM raw.allocations")
    clean = _query("SELECT COUNT(*) AS n FROM clean.allocations")
    assert raw["n"][0] == clean["n"][0]


def test_clean_department_has_real_nulls():
    # Guards transform.py's blank-string-to-NULL conversion - if this ever regressed back to
    # storing "" instead of NULL, isna() would find zero and this test would catch it.
    clean = _query("SELECT patron_department FROM clean.allocations")
    assert clean["patron_department"].isna().sum() > 0


def test_clean_schema_types_and_constraints():
    clean = _query("""
        SELECT allocation_id, patron_department, patron_email_domain,
               renewal_count, resource_count, duration_seconds
        FROM clean.allocations
    """)
    CLEAN_SCHEMA.validate(clean)
