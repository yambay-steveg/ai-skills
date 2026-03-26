"""Tests for analyse_senders.py."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


def _make_msg(msg_id, sender_email, sender_name, subject, is_read=False,
              received="2026-03-25T10:00:00Z"):
    return {
        "id": msg_id,
        "subject": subject,
        "from": {"emailAddress": {"address": sender_email, "name": sender_name}},
        "receivedDateTime": received,
        "isRead": is_read,
    }


# Import the analyse function directly
from importlib.util import spec_from_file_location, module_from_spec
_spec = spec_from_file_location("analyse_senders",
                                 Path(__file__).parent.parent / "scripts" / "analyse_senders.py")
_mod = module_from_spec(_spec)
_spec.loader.exec_module(_mod)
analyse = _mod.analyse


class TestAnalyseSenders:

    def test_empty_input(self):
        result = analyse([])
        assert result["total_messages"] == 0
        assert result["total_senders"] == 0
        assert result["senders"] == []

    def test_single_sender_single_message(self):
        messages = [_make_msg("1", "a@test.com", "Alice", "Hello")]
        result = analyse(messages)
        assert result["total_messages"] == 1
        assert result["total_senders"] == 1
        sender = result["senders"][0]
        assert sender["email"] == "a@test.com"
        assert sender["name"] == "Alice"
        assert sender["total"] == 1
        assert sender["unread"] == 1
        assert sender["read"] == 0
        assert sender["read_rate"] == 0.0

    def test_read_rate_calculation(self):
        messages = [
            _make_msg("1", "a@test.com", "Alice", "Msg 1", is_read=True),
            _make_msg("2", "a@test.com", "Alice", "Msg 2", is_read=True),
            _make_msg("3", "a@test.com", "Alice", "Msg 3", is_read=False),
            _make_msg("4", "a@test.com", "Alice", "Msg 4", is_read=False),
        ]
        result = analyse(messages)
        sender = result["senders"][0]
        assert sender["read_rate"] == 0.5
        assert sender["read"] == 2
        assert sender["unread"] == 2

    def test_multiple_senders_sorted_by_read_rate(self):
        messages = [
            _make_msg("1", "noise@test.com", "Noise", "Spam 1", is_read=False),
            _make_msg("2", "noise@test.com", "Noise", "Spam 2", is_read=False),
            _make_msg("3", "good@test.com", "Good", "Article 1", is_read=True),
            _make_msg("4", "good@test.com", "Good", "Article 2", is_read=True),
        ]
        result = analyse(messages)
        assert result["total_senders"] == 2
        # noise@test.com (0% read) should come first
        assert result["senders"][0]["email"] == "noise@test.com"
        assert result["senders"][0]["read_rate"] == 0.0
        assert result["senders"][1]["email"] == "good@test.com"
        assert result["senders"][1]["read_rate"] == 1.0

    def test_email_case_normalised(self):
        messages = [
            _make_msg("1", "Alice@Test.COM", "Alice", "Msg 1"),
            _make_msg("2", "alice@test.com", "Alice", "Msg 2"),
        ]
        result = analyse(messages)
        assert result["total_senders"] == 1
        assert result["senders"][0]["total"] == 2

    def test_sample_subjects_capped_at_three(self):
        messages = [
            _make_msg("1", "a@t.com", "A", "Sub 1"),
            _make_msg("2", "a@t.com", "A", "Sub 2"),
            _make_msg("3", "a@t.com", "A", "Sub 3"),
            _make_msg("4", "a@t.com", "A", "Sub 4"),
            _make_msg("5", "a@t.com", "A", "Sub 5"),
        ]
        result = analyse(messages)
        assert len(result["senders"][0]["subjects"]) == 3

    def test_date_range_tracked(self):
        messages = [
            _make_msg("1", "a@t.com", "A", "Early", received="2026-01-01T00:00:00Z"),
            _make_msg("2", "a@t.com", "A", "Late", received="2026-03-25T00:00:00Z"),
            _make_msg("3", "a@t.com", "A", "Mid", received="2026-02-15T00:00:00Z"),
        ]
        result = analyse(messages)
        sender = result["senders"][0]
        assert sender["earliest"] == "2026-01-01T00:00:00Z"
        assert sender["latest"] == "2026-03-25T00:00:00Z"

    def test_message_ids_collected(self):
        messages = [
            _make_msg("aaa", "a@t.com", "A", "Msg 1"),
            _make_msg("bbb", "a@t.com", "A", "Msg 2"),
        ]
        result = analyse(messages)
        assert set(result["senders"][0]["message_ids"]) == {"aaa", "bbb"}
