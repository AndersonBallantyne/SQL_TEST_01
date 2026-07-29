import os
from dotenv import load_dotenv
import psycopg
from bs4 import BeautifulSoup

load_dotenv(encoding="utf-8-sig")

SOURCE_FILES = [
    "sql-test-01-cheatsheet.html",
    "PROJECT_DIAGRAMS/project-overview.html",
    "PROJECT_DIAGRAMS/BUILD_1_FLOW/environment-handoff-brief-v2.html",
    "PROJECT_DIAGRAMS/BUILD_1_FLOW/build1-handoff-brief.html",
    "PROJECT_DIAGRAMS/BUILD_2_FLOW/build2-handoff-brief.html",
    "PROJECT_DIAGRAMS/BUILD_2_5_FLOW/build2-5-handoff-brief.html",
    "PROJECT_DIAGRAMS/BUILD_3_FLOW/build3-handoff-brief.html",
    # Added 2026-07-29 - these three existed on disk since Build 3.5/4/5 but were never
    # added here, so search_docs's corpus silently stopped growing after Build 3. Found
    # only because a live question about the project's build history came back stuck at
    # Build 3, not from any automated check (SOURCE_FILES has no directory-scan fallback).
    "PROJECT_DIAGRAMS/BUILD_3_5_FLOW/build3-5-handoff-brief.html",
    "PROJECT_DIAGRAMS/BUILD_4_FLOW/build4-handoff-brief.html",
    "PROJECT_DIAGRAMS/BUILD_5_FLOW/build5-handoff-brief.html",
]


def extract_callout_chunks(soup):
    chunks = []
    for div in soup.select(".callout"):
        text = div.get_text(" ", strip=True)
        if text:
            chunks.append(text)
    for pre in soup.select("pre.code"):
        label = pre.select_one(".fn")
        label_text = label.get_text(strip=True) if label else ""
        code_text = pre.get_text(" ", strip=True)
        chunks.append(f"{label_text}: {code_text}" if label_text else code_text)
    return chunks


def extract_table_row_chunks(soup):
    chunks = []
    for row in soup.select("table.ref tr"):
        cmd = row.select_one("td.cmd")
        desc = row.select_one("td.desc")
        if cmd and desc:
            chunks.append(f"{cmd.get_text(' ', strip=True)}: {desc.get_text(' ', strip=True)}")
    return chunks


def extract_finding_chunks(soup):
    # Build 1's two handoff briefs predate the .callout/pre.code design system -
    # they use .finding/.risk/.vlog/.continuity instead. Same idea, different class names.
    chunks = []
    for div in soup.select(".finding"):
        text = div.get_text(" ", strip=True)
        if text:
            chunks.append(text)
    for div in soup.select(".risk"):
        text = div.get_text(" ", strip=True)
        if text:
            chunks.append(text)
    for div in soup.select(".continuity"):
        text = div.get_text(" ", strip=True)
        if text:
            chunks.append(text)
    for li in soup.select(".vlog li"):
        text = li.get_text(" ", strip=True)
        if text:
            chunks.append(text)
    return chunks


def extract_narrative_chunks(soup):
    # The plain "what/why" prose in every brief's opening section - .lede, .doc-subtitle,
    # .section-note, .phase-goal - never lands in a .callout/.finding/table row, so none
    # of the functions above ever see it. Found via a real relevance-check failure:
    # "what is this project about" surfaced nothing useful because the actual answer
    # text was never chunked in the first place.
    chunks = []
    for selector in (".lede", ".doc-subtitle", ".section-note", ".phase-goal"):
        for el in soup.select(selector):
            text = el.get_text(" ", strip=True)
            if text:
                chunks.append(text)
    return chunks


conn = psycopg.connect(
    host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
    port=5432,
    dbname=os.environ["POSTGRES_DB"],
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
)

for path in SOURCE_FILES:
    with open(path, encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    chunks = (
        extract_callout_chunks(soup)
        + extract_table_row_chunks(soup)
        + extract_finding_chunks(soup)
        + extract_narrative_chunks(soup)
    )

    with conn.cursor() as cur:
        # Delete this file's old chunks first so re-running after editing a source doc
        # replaces its chunks instead of accumulating duplicates alongside them.
        cur.execute("DELETE FROM docs.chunks WHERE source_file = %s", (path,))
        cur.executemany(
            "INSERT INTO docs.chunks (source_file, chunk_text) VALUES (%s, %s)",
            [(path, chunk) for chunk in chunks],
        )
    conn.commit()
    print(f"{path}: {len(chunks)} chunk(s) extracted.")

conn.close()
