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
    "docs/project-overview-v2.html",
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


# tools.py's MAX_FIELD_CHARS (500) truncates any field a live query returns - a chunk longer
# than that isn't just imprecise for retrieval, it can silently lose whatever comes after the
# cutoff. Confirmed real 2026-08-10: a 3,303-char incident chunk, written problem-first,
# resolution-second, got cut off right before the word "Fixed" - a "list open items" answer
# then reported an already-closed incident as still unresolved, and the verifier had no way to
# catch it, since the claim really was consistent with the (incomplete) evidence it saw.
# Patching that one entry's wording fixed that one question; it did nothing for the other 126
# chunks already over 500 chars, or the next one this callout-per-chunk strategy produces.
# Splitting every long chunk at extraction time - not query time - fixes the actual mechanism:
# no chunk this pipeline ever produces can be long enough to have anything truncated out of it.
CHUNK_SPLIT_TARGET_CHARS = 450


def _split_long_text(text, max_len=CHUNK_SPLIT_TARGET_CHARS):
    if len(text) <= max_len:
        return [text]
    # Split on sentence boundaries, not an arbitrary character offset, so a split piece is
    # still a coherent standalone sentence rather than a fragment cut off mid-clause.
    sentences = text.split(". ")
    pieces = []
    current = ""
    for i, sentence in enumerate(sentences):
        piece = sentence if i == len(sentences) - 1 else sentence + ". "
        if current and len(current) + len(piece) > max_len:
            pieces.append(current.strip())
            current = piece
        else:
            current += piece
    if current.strip():
        pieces.append(current.strip())
    # A single sentence can itself exceed max_len (this project's prose leans on em-dashes over
    # periods) - the sentence-boundary split above wouldn't catch that. Hard-wrap anything still
    # oversized on whitespace so the size guarantee holds unconditionally, not "usually."
    final_pieces = []
    for piece in pieces:
        if len(piece) <= max_len:
            final_pieces.append(piece)
            continue
        words = piece.split(" ")
        current_piece = ""
        for word in words:
            candidate = f"{current_piece} {word}".strip()
            if current_piece and len(candidate) > max_len:
                final_pieces.append(current_piece)
                current_piece = word
            else:
                current_piece = candidate
        if current_piece:
            final_pieces.append(current_piece)
    return final_pieces


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


def extract_list_chunks(soup):
    # Same gap extract_narrative_chunks was built to close, for a different shape - bullet
    # feature lists (.feature-list li) and definition-list build breakdowns (.build-list
    # dt/dd pairs), introduced in project-overview-v2.html (2026-08-10), don't land in any
    # of the shapes above either. Found the same way: swapping that file into SOURCE_FILES
    # only actually extracted its 3 .lede paragraphs - every feature and every build's
    # description went unindexed with no error or warning, silently searchable as nothing.
    chunks = []
    for li in soup.select(".feature-list li"):
        text = li.get_text(" ", strip=True)
        if text:
            chunks.append(text)
    for dl in soup.select(".build-list"):
        # dt/dd are siblings, not nested - zip() pairs them positionally, which holds only
        # because every dt here is followed by exactly one dd (true today, not enforced).
        for label, desc in zip(dl.find_all("dt"), dl.find_all("dd")):
            label_text = label.get_text(" ", strip=True)
            desc_text = desc.get_text(" ", strip=True)
            if label_text and desc_text:
                chunks.append(f"{label_text}: {desc_text}")
    return chunks


def main():
    # Guarded behind __main__ (was previously module-level, unconditional) - a pure helper
    # like _split_long_text should be importable (for tests, for reuse) without opening a live
    # database connection and re-extracting every doc as a side effect of the import itself.
    conn = psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=5432,
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )

    with conn.cursor() as cur:
        # A source file removed from SOURCE_FILES (renamed, replaced, deleted) would
        # otherwise keep its old chunks forever - the per-path DELETE below only ever
        # fires for a path this run is about to re-extract, never one it's no longer told
        # to touch. Confirmed real, not hypothetical: swapping project-overview.html for
        # project-overview-v2.html (2026-08-10) left 9 rows stranded under the old path
        # with no cleanup path - the same "orphaned rows" bug shape the 2026-08-05 repo
        # audit already found once, in PROJECT_DIAGRAMS's old paths after that reorg.
        cur.execute("DELETE FROM docs.chunks WHERE NOT (source_file = ANY(%s))", (SOURCE_FILES,))
    conn.commit()

    for path in SOURCE_FILES:
        with open(path, encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")

        chunks = (
            extract_callout_chunks(soup)
            + extract_table_row_chunks(soup)
            + extract_finding_chunks(soup)
            + extract_narrative_chunks(soup)
            + extract_list_chunks(soup)
        )
        # Applied once, centrally, after every extraction function - not inside each one - so
        # the size guarantee covers every chunk this pipeline ever produces, not just the ones
        # from whichever function happened to get patched when one chunk caused one problem.
        chunks = [piece for chunk in chunks for piece in _split_long_text(chunk)]

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


if __name__ == "__main__":
    main()
