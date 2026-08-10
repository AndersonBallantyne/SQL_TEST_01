from extract_doc_chunks import _split_long_text, CHUNK_SPLIT_TARGET_CHARS


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
