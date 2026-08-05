import glob
import os
from dotenv import load_dotenv
import psycopg
from bs4 import BeautifulSoup

load_dotenv(encoding="utf-8-sig")

# Handoff briefs are auto-discovered by glob, not hand-listed - a hardcoded list here
# silently stopped growing after Build 3 (found 2026-07-29, three missing briefs), then
# missed Build 6's brief entirely the same day it was written (found 2026-07-31, while
# verifying "are the agent's docs current"). Same root cause both times: a manual list
# with no directory-scan fallback. Fixed at the root this time instead of patched again -
# every file matching this glob is included automatically, present and future.
# Paths are relative to the repo root (CWD when this script is invoked as
# `python src/extract_doc_chunks.py`, matching every other script in this project), not to
# this file's own location in src/ - docs/ was PROJECT_DIAGRAMS/ before the 2026-08-05 reorg.
SOURCE_FILES = [
    "docs/sql-test-01-cheatsheet.html",
    "docs/project-overview.html",
] + sorted(
    # glob returns os.sep-joined paths - backslash on Windows - which would silently create
    # a second, duplicate set of rows under a different source_file string every time this
    # runs on Windows vs. however it ran before. Normalized to "/" so source_file stays a
    # stable key across OSes and reruns, matching every other path string in this file.
    path.replace(os.sep, "/")
    for path in glob.glob("docs/**/*handoff-brief*.html", recursive=True)
)


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
