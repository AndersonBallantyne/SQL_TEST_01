from bs4 import BeautifulSoup
from extract_doc_chunks import _split_long_text, CHUNK_SPLIT_TARGET_CHARS, extract_list_chunks, extract_numbered_row_chunks


def test_short_text_passes_through_unchanged():
    text = "A short entry, well under the limit."
    assert _split_long_text(text) == [text]


def test_long_text_splits_on_sentence_boundaries():
    sentence = "This is one sentence of moderate length, written in this project's own style. "
    text = sentence * 15  # comfortably over CHUNK_SPLIT_TARGET_CHARS
    pieces = _split_long_text(text)

    assert len(pieces) > 1
    for piece in pieces:
        assert len(piece) <= CHUNK_SPLIT_TARGET_CHARS
    # No content lost or reordered - rejoining every piece reconstructs the original sentences.
    rejoined = " ".join(pieces)
    assert rejoined.replace("  ", " ") == text.strip().replace("  ", " ")


def test_every_split_piece_stays_under_max_field_chars():
    # The whole point of this fix: no chunk this pipeline produces should ever be long enough
    # for tools.py's MAX_FIELD_CHARS (500) to truncate it - this is the actual invariant that
    # matters, checked directly against that real number, not just the internal target constant.
    long_text = "A dense incident narrative sentence with real detail in it. " * 20
    for piece in _split_long_text(long_text):
        assert len(piece) <= 500


def test_a_single_oversized_sentence_still_gets_hard_wrapped():
    # This project's prose leans on em-dashes over periods, so a single "sentence" (no period
    # until the very end) can itself exceed the target - the word-boundary fallback must still
    # produce pieces at or under the limit, not just skip splitting because there's no period.
    one_giant_sentence = "word " * 200 + "."
    assert len(one_giant_sentence) > CHUNK_SPLIT_TARGET_CHARS

    pieces = _split_long_text(one_giant_sentence)
    assert len(pieces) > 1
    for piece in pieces:
        assert len(piece) <= CHUNK_SPLIT_TARGET_CHARS


def test_splitting_preserves_all_words_no_loss():
    one_giant_sentence = " ".join(f"word{i}" for i in range(150)) + "."
    pieces = _split_long_text(one_giant_sentence)
    rejoined_words = " ".join(pieces).split(" ")
    original_words = one_giant_sentence.split(" ")
    assert rejoined_words == original_words


def test_extract_list_chunks_captures_feature_list_items():
    # project-overview-v2.html's shape (2026-08-10) - bullet feature lists don't land in any
    # of the other extraction functions (.callout/.finding/table.ref/.lede), which is exactly
    # how a real swap of this file into SOURCE_FILES silently extracted only 3 of its 21
    # actual chunks before this function existed.
    soup = BeautifulSoup(
        '<ul class="feature-list"><li><b>Self-verification.</b> Checked by a second agent.</li>'
        '<li><b>Full cost observability.</b> Every call is logged.</li></ul>',
        "html.parser",
    )
    chunks = extract_list_chunks(soup)
    assert chunks == [
        "Self-verification. Checked by a second agent.",
        "Full cost observability. Every call is logged.",
    ]


def test_extract_list_chunks_pairs_build_list_dt_dd_by_position():
    soup = BeautifulSoup(
        '<dl class="build-list"><dt>Build 1</dt><dd>The agent itself.</dd>'
        "<dt>Build 2</dt><dd>The data pipeline.</dd></dl>",
        "html.parser",
    )
    chunks = extract_list_chunks(soup)
    assert chunks == ["Build 1: The agent itself.", "Build 2: The data pipeline."]


def test_extract_list_chunks_drops_a_trailing_unmatched_dt():
    # Documents the real limitation named in extract_list_chunks' own comment: zip() pairs
    # positionally and silently stops at the shorter list - a dt with no matching dd doesn't
    # error, it just never becomes a chunk. Not a hidden bug: proven here so a future change
    # to this pairing logic has something concrete to break against.
    soup = BeautifulSoup(
        '<dl class="build-list"><dt>Build 1</dt><dd>The agent itself.</dd><dt>Build 2</dt></dl>',
        "html.parser",
    )
    chunks = extract_list_chunks(soup)
    assert chunks == ["Build 1: The agent itself."]


def test_extract_numbered_row_chunks_prefixes_each_row_with_its_date():
    # sql-test-01-commit-log.html's shape (2026-08-11) - td.num/td.desc rows, not td.cmd/
    # td.desc, so extract_table_row_chunks() silently skips every row here (its td.cmd
    # selector never matches), the same "added to SOURCE_FILES, extracted zero chunks, no
    # error" shape the feature-list/build-list gap above already proved once.
    soup = BeautifulSoup(
        '<section class="group" id="2026-08-11">'
        '<div class="group-head"><h2>2026-08-11</h2></div>'
        '<table class="ref"><tbody>'
        '<tr><td class="num">1</td><td class="desc">First commit of the day</td></tr>'
        '<tr><td class="num">2</td><td class="desc">Second commit of the day</td></tr>'
        "</tbody></table></section>",
        "html.parser",
    )
    chunks = extract_numbered_row_chunks(soup)
    assert chunks == [
        "2026-08-11, commit 1: First commit of the day",
        "2026-08-11, commit 2: Second commit of the day",
    ]


def test_extract_numbered_row_chunks_keeps_same_numbers_from_different_dates_distinct():
    # td.num restarts at 1 for every date group - without the date prefix, "commit 1" from
    # two different days would be indistinguishable chunks, silently conflating unrelated
    # commits the moment the file covers more than one day.
    soup = BeautifulSoup(
        '<section class="group" id="2026-07-01">'
        '<div class="group-head"><h2>2026-07-01</h2></div>'
        '<table class="ref"><tbody>'
        '<tr><td class="num">1</td><td class="desc">Oldest commit</td></tr>'
        "</tbody></table></section>"
        '<section class="group" id="2026-08-11">'
        '<div class="group-head"><h2>2026-08-11</h2></div>'
        '<table class="ref"><tbody>'
        '<tr><td class="num">1</td><td class="desc">Newest commit</td></tr>'
        "</tbody></table></section>",
        "html.parser",
    )
    chunks = extract_numbered_row_chunks(soup)
    assert chunks == [
        "2026-07-01, commit 1: Oldest commit",
        "2026-08-11, commit 1: Newest commit",
    ]


def test_extract_numbered_row_chunks_ignores_td_cmd_rows():
    # The cheat sheet's command-reference rows (td.cmd/td.desc) live under this same
    # table.ref selector - confirms this function only ever matches td.num rows and doesn't
    # double-extract command rows that extract_table_row_chunks() already covers.
    soup = BeautifulSoup(
        '<section class="group"><div class="group-head"><h2>ref</h2></div>'
        '<table class="ref"><tbody>'
        '<tr><td class="cmd">git log</td><td class="desc">Recent commit history</td></tr>'
        "</tbody></table></section>",
        "html.parser",
    )
    assert extract_numbered_row_chunks(soup) == []
