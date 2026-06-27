"""Unit tests for search filter construction (no network)."""

import argparse
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import search_email


def _args(**kw):
    defaults = dict(text=None, from_=None, to=None, subject=None, body=None,
                    mailbox=None, after=None, before=None, unread=False)
    defaults.update(kw)
    return argparse.Namespace(**defaults)


def test_to_utc_date_only():
    assert search_email._to_utc("2026-05-01") == "2026-05-01T00:00:00Z"


def test_to_utc_passthrough_timestamp():
    ts = "2026-05-01T12:30:00Z"
    assert search_email._to_utc(ts) == ts


def test_single_condition_not_wrapped():
    flt = search_email.build_filter(None, _args(text="invoice"))
    assert flt == {"text": "invoice"}


def test_multiple_conditions_anded():
    flt = search_email.build_filter(None, _args(from_="bp.com", after="2026-05-01"))
    assert flt["operator"] == "AND"
    assert {"from": "bp.com"} in flt["conditions"]
    assert {"after": "2026-05-01T00:00:00Z"} in flt["conditions"]


def test_unread_uses_not_keyword():
    flt = search_email.build_filter(None, _args(unread=True))
    assert flt == {"notKeyword": "$seen"}


def test_no_filters_exits():
    with pytest.raises(SystemExit):
        search_email.build_filter(None, _args())
