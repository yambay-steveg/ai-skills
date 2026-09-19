"""Unit tests for attachment naming and selection (no network)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import download_attachment as da


def _att(name=None, type_="application/pdf", size=10, blob_id="B1"):
    return {"name": name, "type": type_, "size": size, "blobId": blob_id}


def test_slugify_kebab_cases_and_keeps_extension():
    assert da.slugify("STEVE GODDING - CSV CUTLIST TEMPLATE.pdf") == \
        "steve-godding-csv-cutlist-template.pdf"


def test_slugify_no_extension():
    assert da.slugify("Quote For Steve") == "quote-for-steve"


def test_slugify_collapses_punctuation():
    assert da.slugify("Invoice #1234 (final)_v2.PDF") == "invoice-1234-final-v2.pdf"


def test_slugify_falls_back_when_stem_is_all_punctuation():
    assert da.slugify("!!!.pdf") == "attachment.pdf"


def test_keep_name_leaves_the_name_alone():
    assert da.attachment_filename(_att("A Quote.pdf"), 0, keep_name=True) == "A Quote.pdf"


def test_unnamed_attachment_gets_positional_name_with_guessed_extension():
    assert da.attachment_filename(_att(None, "application/pdf"), 2, keep_name=True) == \
        "attachment-2.pdf"


def test_unnamed_attachment_unknown_type_falls_back_to_bin():
    assert da.attachment_filename(_att("", "application/x-nonsense"), 0,
                                  keep_name=True) == "attachment-0.bin"


def test_path_components_in_a_sender_supplied_name_are_stripped():
    assert da.attachment_filename(_att("../../etc/passwd"), 0, keep_name=True) == "passwd"


def test_select_defaults_to_every_attachment():
    atts = [_att("a.pdf"), _att("b.pdf")]
    assert da.select(atts, None, None) == [(0, atts[0]), (1, atts[1])]


def test_select_by_index():
    atts = [_att("a.pdf"), _att("b.pdf")]
    assert da.select(atts, None, 1) == [(1, atts[1])]


def test_select_by_name_is_case_insensitive():
    atts = [_att("a.pdf"), _att("Quote.PDF")]
    assert da.select(atts, "quote.pdf", None) == [(1, atts[1])]


def test_select_by_name_returns_every_match():
    atts = [_att("dup.pdf"), _att("dup.pdf")]
    assert len(da.select(atts, "dup.pdf", None)) == 2


def test_select_out_of_range_index_exits():
    with pytest.raises(SystemExit):
        da.select([_att("a.pdf")], None, 5)


def test_select_unknown_name_exits():
    with pytest.raises(SystemExit):
        da.select([_att("a.pdf")], "missing.pdf", None)


def _inline(name):
    a = _att(name, "image/png")
    a["disposition"] = "inline"
    return a


def _real(name):
    a = _att(name)
    a["disposition"] = "attachment"
    return a


def test_download_all_skips_inline_parts():
    atts = [_inline("sig.png"), _real("quote.pdf")]
    assert da.select(atts, None, None) == [(1, atts[1])]


def test_indexes_survive_the_inline_filter():
    atts = [_inline("sig.png"), _real("a.pdf"), _real("b.pdf")]
    assert [i for i, _ in da.select(atts, None, None)] == [1, 2]


def test_include_inline_keeps_everything():
    atts = [_inline("sig.png"), _real("quote.pdf")]
    assert len(da.select(atts, None, None, include_inline=True)) == 2


def test_explicit_index_reaches_an_inline_part():
    atts = [_inline("sig.png"), _real("quote.pdf")]
    assert da.select(atts, None, 0) == [(0, atts[0])]


def test_explicit_name_reaches_an_inline_part():
    atts = [_inline("sig.png"), _real("quote.pdf")]
    assert da.select(atts, "sig.png", None) == [(0, atts[0])]


def test_all_inline_exits_with_a_hint():
    with pytest.raises(SystemExit):
        da.select([_inline("sig.png")], None, None)
