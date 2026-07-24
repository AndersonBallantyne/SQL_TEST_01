import os
import random
from dotenv import load_dotenv
import psycopg

load_dotenv(encoding="utf-8-sig")

REAL_DOMAIN = "artschool.edu"
FIXTURE_DOMAIN = "fixture.edu"

# The real->fake department mapping lives in department_mapping.local.py, a git-ignored file
# NOT committed to this repo - it's the real department codes as dictionary keys, and this
# script itself is public, so the mapping can't live here directly. See
# DEPARTMENT_MAPPING.local.md for the human-readable reference copy (also git-ignored).
# A literal dot in the filename isn't a valid dotted import path, hence loading it by file
# path directly rather than a normal `import`.
import importlib.util as _importlib_util

_spec = _importlib_util.spec_from_file_location("department_mapping_local", "department_mapping.local.py")
_department_mapping_local = _importlib_util.module_from_spec(_spec)
_spec.loader.exec_module(_department_mapping_local)
DEPARTMENT_MAP = _department_mapping_local.DEPARTMENT_MAP

# Synthetic equipment pool, same broad categories as the real inventory (mirrorless/DSLR
# cameras + accessories, audio recorders/mics/cables, laptops + chargers, graphics tablets,
# LED lighting, projectors, general AV cables/power, VR/360 cameras) but different specific
# brand/model combinations than what this institution actually owns - real camera/laptop
# brands are generic commercial product categories, not the institution's proprietary data;
# what's proprietary is their specific real inventory list and internal tag numbers, not the
# fact that "cameras exist" as an equipment category.
EQUIPMENT_POOL = [
    ("NIKON Z6 III MIRRORLESS BODY", "NIKON Z6III"),
    ("NIKON Z6 III BATTERY", "NIKON Z6III BATT"),
    ("NIKON Z6 III BATTERY CHARGER", "NIKON Z6III CHRG"),
    ("NIKON Z6 III CAMERA CASE", "NIKON Z6III CASE"),
    ("FUJIFILM X-T5 BODY", "FUJI XT5"),
    ("FUJIFILM X-T5 BATTERY", "FUJI XT5 BATT"),
    ("FUJIFILM 18-55mm LENS", "FUJI 1855 LENS"),
    ("OLYMPUS OM-D E-M1 BODY", "OLY EM1"),
    ("OLYMPUS 12-40mm LENS", "OLY 1240 LENS"),
    ("PANASONIC S5 II BODY", "PANA S5II"),
    ("PANASONIC S5 II BATTERY CHARGER", "PANA S5II CHRG"),
    ("SANDISK 64GB SD CARD", "SANDISK 64SD"),
    ("SANDISK 128GB SD CARD", "SANDISK 128SD"),
    ("LEXAR 128GB CF CARD", "LEXAR CF128"),
    ("MANFROTTO TRIPOD", "MANFRO TRIPOD"),
    ("MANFROTTO TRIPOD CASE", "MANFRO CASE"),
    ("RODE WIRELESS MIC", "RODE WIRELESS"),
    ("RODE MIC BATTERY", "RODE MIC BATT"),
    ("ZOOM H5 RECORDER", "ZOOM H5"),
    ("ZOOM H5 RECORDER CASE", "ZOOM H5 CASE"),
    ("XLR CABLE 15FT", "XLR15"),
    ("XLR CABLE 25FT", "XLR25"),
    ("AUDIO-TECHNICA HEADPHONES", "AT HEADPHONES"),
    ("DELL XPS LAPTOP", "DELL XPS"),
    ("DELL XPS LAPTOP CHARGER", "DELL XPS CHRG"),
    ("MACBOOK AIR M3 LAPTOP", "MBA M3"),
    ("MACBOOK AIR M3 CHARGER", "MBA M3 CHRG"),
    ("MACBOOK AIR CHARGING CABLE", "MBA CABLE"),
    ("LAPTOP SLEEVE CASE", "LAPTOP SLEEVE"),
    ("USB-C MULTIPORT HUB", "USBC HUB"),
    ("USB-C TO HDMI ADAPTER", "USBC HDMI"),
    ("WACOM CINTIQ TABLET", "WACOM CINTIQ"),
    ("WACOM CINTIQ PEN", "WACOM CINTIQ PEN"),
    ("WACOM ONE TABLET", "WACOM ONE"),
    ("HUION DRAWING TABLET", "HUION TABLET"),
    ("GODOX LED LIGHT PANEL", "GODOX LED"),
    ("GODOX LIGHT STAND", "GODOX STAND"),
    ("GODOX POWER SUPPLY", "GODOX PSU"),
    ("EPSON PROJECTOR", "EPSON PROJ"),
    ("EPSON PROJECTOR HDMI CABLE", "EPSON PROJ HDMI"),
    ("BENQ DATA PROJECTOR", "BENQ PROJ"),
    ("HDMI CABLE 10FT", "HDMI10"),
    ("EXTENSION CORD 10FT", "EXTCORD10"),
    ("POWER STRIP", "PWRSTRIP"),
    ("LOGITECH WEBCAM", "LOGI WEBCAM"),
    ("LOGITECH WIRELESS MOUSE", "LOGI MOUSE"),
    ("USB KEYBOARD", "USB KYBD"),
    ("CARD READER", "CARDRDR"),
    ("EQUIPMENT CRATE 12x12", "CRATE12"),
    ("META QUEST HEADSET", "MQUEST HS"),
    ("META QUEST CONTROLLER", "MQUEST CTRL"),
    ("META QUEST CHARGING CABLE", "MQUEST CABLE"),
    ("INSTA360 X4 CAMERA", "INSTA X4"),
    ("INSTA360 X4 BATTERY", "INSTA X4 BATT"),
    ("INSTA360 X4 CASE", "INSTA X4 CASE"),
]


def load_real_rows(limit=None, order="random()"):
    conn = psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=5432,
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )
    with conn.cursor() as cur:
        q = f"""
            SELECT allocation_id, patron_department, patron_email, renewal_count,
                   actual_start, scheduled_end, actual_end, duration, resource_count, summary
            FROM raw.allocations ORDER BY {order}
        """
        if limit:
            q += f" LIMIT {limit}"
        cur.execute(q)
        rows = cur.fetchall()
    conn.close()
    return rows


def mask_email(email):
    return email.replace(REAL_DOMAIN, FIXTURE_DOMAIN)


def synth_department(dept):
    if not dept or not dept.strip():
        return dept
    return DEPARTMENT_MAP.get(dept, dept)


def synth_summary(resource_count, tag_counter):
    try:
        n = max(int(resource_count), 1)
    except (TypeError, ValueError):
        n = 1
    items = random.choices(EQUIPMENT_POOL, k=n)
    parts = [f"{name} - {code}-{next(tag_counter)}" for name, code in items]
    return "Returned: " + " | ".join(parts) + " | "


def tag_counter_gen(start=100000):
    n = start
    while True:
        yield n
        n += 1


import csv
import sys

OUTPUT_PATH = "data/ALLOCATION-synthesized.csv"
# 7-digit range, categorically different length from the real 6-digit IDs observed
# (roughly 8xxxxx) - sampled without replacement so every fake ID is unique, and randomly
# assigned rather than sequential so the ID itself doesn't leak each row's position/order in
# the original real export.
FAKE_ID_RANGE = range(1_000_000, 10_000_000)

FIELDNAMES = [
    "Allocation", "Patron Department", "Patron Email", "Renewal Count",
    "Actual Start", "Scheduled End", "Actual End", "Duration",
    "Resource Count", "Summary",
]


def generate_full_dataset():
    random.seed(42)
    tag_counter = tag_counter_gen()
    # Deterministic order (real allocation_id, ascending) for the row content itself - this is
    # a full 1:1 transform of every real row, not a sample, so there's no reason to shuffle
    # row order; only the fake IDs assigned to each row are randomized.
    rows = load_real_rows(order="allocation_id")
    fake_ids = random.sample(FAKE_ID_RANGE, len(rows))

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for fake_id, row in zip(fake_ids, rows):
            (real_id, dept, email, renewal, start, sched_end, actual_end,
             duration, resource_count, summary) = row
            writer.writerow({
                "Allocation": fake_id,
                "Patron Department": synth_department(dept),
                "Patron Email": mask_email(email),
                "Renewal Count": renewal,
                "Actual Start": start,
                "Scheduled End": sched_end,
                "Actual End": actual_end,
                "Duration": duration,
                "Resource Count": resource_count,
                "Summary": synth_summary(resource_count, tag_counter),
            })

    print(f"Wrote {len(rows)} synthesized rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--full":
        generate_full_dataset()
    else:
        random.seed(42)
        tag_counter = tag_counter_gen()
        rows = load_real_rows(limit=8)
        fake_ids = random.sample(FAKE_ID_RANGE, len(rows))

        print(f"{'ALLOCATION':<12}{'DEPT':<6}{'EMAIL':<24}{'RENEW':<7}{'RESRC':<7}")
        print("-" * 90)
        for fake_id, row in zip(fake_ids, rows):
            (real_id, dept, email, renewal, start, sched_end, actual_end, duration, resource_count, summary) = row
            new_dept = synth_department(dept)
            new_email = mask_email(email)
            new_summary = synth_summary(resource_count, tag_counter)

            print(f"{fake_id:<12}{(new_dept or ''):<6}{new_email:<24}{renewal:<7}{resource_count:<7}")
            print(f"  real dates (unchanged): {start} -> {sched_end} -> {actual_end}, duration={duration}")
            print(f"  synth summary: {new_summary}")
            print()
