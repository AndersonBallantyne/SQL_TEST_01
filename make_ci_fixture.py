import csv
import os
import re
from dotenv import load_dotenv
import psycopg

load_dotenv(encoding="utf-8-sig")

FIXTURE_ROW_COUNT = 30
OUTPUT_PATH = "ci_fixture/ALLOCATION-fixture.csv"
REAL_DOMAIN = "artschool.edu"
FIXTURE_DOMAIN = "fixture.edu"
FAKE_ID_START = 9000001

conn = psycopg.connect(
    host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
    port=5432,
    dbname=os.environ["POSTGRES_DB"],
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
)

with conn.cursor() as cur:
    # ORDER BY random() gives a cross-section of departments/domains/equipment types rather
    # than the first N rows, which would all be one narrow time slice of the real export.
    cur.execute(
        """
        SELECT allocation_id, patron_department, patron_email, renewal_count,
               actual_start, scheduled_end, actual_end, duration,
               resource_count, summary
        FROM raw.allocations
        ORDER BY random()
        LIMIT %s
        """,
        (FIXTURE_ROW_COUNT,),
    )
    rows = cur.fetchall()
conn.close()


def mask_email(email):
    # Preserves the inside./alumni. subdomain structure - real categorical signal kept on
    # purpose, same reasoning as the original artcenter.edu -> artschool.edu mask - only the
    # base institution domain is swapped, and only for this public CI-fixture subset. A small
    # minority of real rows use gmail.com instead - left as-is (generic public provider, not
    # identifying, and not the institution's own domain), per explicit user direction.
    return email.replace(REAL_DOMAIN, FIXTURE_DOMAIN)


def make_summary_masker():
    # Real summaries embed the institution's actual internal asset-tag numbers inline with
    # the equipment description, e.g. "CAMERA BAG-BoP-83094". The equipment-category text is
    # generic and safe to keep (useful for realistic embedding tests); the numeric tag itself
    # is real operational data and gets scrubbed to a fake same-length number, using a counter
    # closed over in this factory so every scrubbed tag in the fixture is unique.
    counter = iter(range(500000, 600000))

    def mask(summary):
        def replace_digits(match):
            fake = str(next(counter))
            return fake.zfill(len(match.group(0)))[-len(match.group(0)):]

        return re.sub(r"\d{4,}", replace_digits, summary)

    return mask


mask_summary = make_summary_masker()

fieldnames = [
    "Allocation", "Patron Department", "Patron Email", "Renewal Count",
    "Actual Start", "Scheduled End", "Actual End", "Duration",
    "Resource Count", "Summary",
]

os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for i, row in enumerate(rows):
        (allocation_id, patron_department, patron_email, renewal_count,
         actual_start, scheduled_end, actual_end, duration,
         resource_count, summary) = row
        writer.writerow({
            "Allocation": FAKE_ID_START + i,
            "Patron Department": patron_department,
            "Patron Email": mask_email(patron_email),
            "Renewal Count": renewal_count,
            "Actual Start": actual_start,
            "Scheduled End": scheduled_end,
            "Actual End": actual_end,
            "Duration": duration,
            "Resource Count": resource_count,
            "Summary": mask_summary(summary),
        })

print(f"Wrote {len(rows)} masked fixture rows to {OUTPUT_PATH}")
