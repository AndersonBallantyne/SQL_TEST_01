import os
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

# The full, closed universe of distinct item names found in clean.allocations.summary, each
# mapped to (category, is_accessory) - derived from a one-time audit of every summary value in
# the table (2026-08-06), not guessed. If a name shows up in the data that isn't in this map,
# the run below fails loudly rather than silently miscategorizing it as an accident of a keyword
# match, which is exactly the class of bug this table exists to eliminate.
ITEM_CLASSIFICATION = {
    "AUDIO-TECHNICA HEADPHONES": ("headphones", False),
    "BENQ DATA PROJECTOR": ("projector", False),
    "CARD READER": ("card_reader", False),
    "DELL XPS LAPTOP": ("laptop", False),
    "DELL XPS LAPTOP CHARGER": ("laptop", True),
    "EPSON PROJECTOR": ("projector", False),
    "EPSON PROJECTOR HDMI CABLE": ("projector", True),
    "EQUIPMENT CRATE 12x12": ("crate", False),
    "EXTENSION CORD 10FT": ("power", False),
    "FUJIFILM 18-55mm LENS": ("camera", True),
    "FUJIFILM X-T5 BATTERY": ("camera", True),
    "FUJIFILM X-T5 BODY": ("camera", False),
    "GODOX LED LIGHT PANEL": ("lighting", False),
    "GODOX LIGHT STAND": ("lighting", True),
    "GODOX POWER SUPPLY": ("lighting", True),
    "HDMI CABLE 10FT": ("cable", False),
    "HUION DRAWING TABLET": ("drawing_tablet", False),
    "INSTA360 X4 BATTERY": ("camera", True),
    "INSTA360 X4 CAMERA": ("camera", False),
    "INSTA360 X4 CASE": ("camera", True),
    "LAPTOP SLEEVE CASE": ("laptop", True),
    "LEXAR 128GB CF CARD": ("memory_card", False),
    "LOGITECH WEBCAM": ("webcam", False),
    "LOGITECH WIRELESS MOUSE": ("mouse", False),
    "MACBOOK AIR CHARGING CABLE": ("laptop", True),
    "MACBOOK AIR M3 CHARGER": ("laptop", True),
    "MACBOOK AIR M3 LAPTOP": ("laptop", False),
    "MANFROTTO TRIPOD": ("tripod", False),
    "MANFROTTO TRIPOD CASE": ("tripod", True),
    "META QUEST CHARGING CABLE": ("vr_headset", True),
    "META QUEST CONTROLLER": ("vr_headset", True),
    "META QUEST HEADSET": ("vr_headset", False),
    "NIKON Z6 III BATTERY": ("camera", True),
    "NIKON Z6 III BATTERY CHARGER": ("camera", True),
    "NIKON Z6 III CAMERA CASE": ("camera", True),
    "NIKON Z6 III MIRRORLESS BODY": ("camera", False),
    "OLYMPUS 12-40mm LENS": ("camera", True),
    "OLYMPUS OM-D E-M1 BODY": ("camera", False),
    "PANASONIC S5 II BATTERY CHARGER": ("camera", True),
    "PANASONIC S5 II BODY": ("camera", False),
    "POWER STRIP": ("power", False),
    "RODE MIC BATTERY": ("microphone", True),
    "RODE WIRELESS MIC": ("microphone", False),
    "SANDISK 128GB SD CARD": ("memory_card", False),
    "SANDISK 64GB SD CARD": ("memory_card", False),
    "USB KEYBOARD": ("keyboard", False),
    "USB-C MULTIPORT HUB": ("adapter", False),
    "USB-C TO HDMI ADAPTER": ("adapter", False),
    "WACOM CINTIQ PEN": ("drawing_tablet", True),
    "WACOM CINTIQ TABLET": ("drawing_tablet", False),
    "WACOM ONE TABLET": ("drawing_tablet", False),
    "XLR CABLE 15FT": ("cable", False),
    "XLR CABLE 25FT": ("cable", False),
    "ZOOM H5 RECORDER": ("audio_recorder", False),
    "ZOOM H5 RECORDER CASE": ("audio_recorder", True),
}

with conn.cursor() as cur:
    cur.execute("SELECT allocation_id, summary FROM clean.allocations")
    allocations = cur.fetchall()

rows = []
unknown_names = set()
for allocation_id, summary in allocations:
    if not summary:
        continue
    s = summary.strip()
    is_returned = s.startswith("Returned:")
    if is_returned:
        s = s[len("Returned:"):].strip()

    for part in s.split("|"):
        part = part.strip()
        if not part or " - " not in part:
            continue
        item_name, tag = part.split(" - ", 1)
        item_name = item_name.strip()
        tag = tag.strip()

        classification = ITEM_CLASSIFICATION.get(item_name)
        if classification is None:
            unknown_names.add(item_name)
            continue
        category, is_accessory = classification
        rows.append((allocation_id, item_name, category, is_accessory, is_returned, tag))

if unknown_names:
    conn.close()
    raise ValueError(
        f"{len(unknown_names)} item name(s) found in the data with no entry in "
        f"ITEM_CLASSIFICATION: {sorted(unknown_names)}. Add them before re-running."
    )

with conn.cursor() as cur:
    # Idempotent/re-runnable - a full rebuild each time (same philosophy as
    # 005_clean_schema.sql's clean layer), not an incremental load, since the source is a
    # closed, already-fully-read set of summary strings rather than a growing raw feed.
    cur.execute("TRUNCATE TABLE clean.allocation_items RESTART IDENTITY")
    cur.executemany(
        """
        INSERT INTO clean.allocation_items
            (allocation_id, item_name, category, is_accessory, is_returned, tag)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        rows,
    )
conn.commit()
conn.close()

print(f"Loaded {len(rows)} item row(s) into clean.allocation_items from {len(allocations)} allocation(s).")
