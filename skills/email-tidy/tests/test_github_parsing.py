"""Tests for GitHub header parsing logic in fetch_github_headers.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from importlib.util import spec_from_file_location, module_from_spec
_spec = spec_from_file_location("fetch_github_headers",
                                 Path(__file__).parent.parent / "scripts" / "fetch_github_headers.py")
_mod = module_from_spec(_spec)
_spec.loader.exec_module(_mod)
extract_github_metadata = _mod.extract_github_metadata


def _make_msg(subject="", headers=None):
    msg = {"subject": subject, "internetMessageHeaders": headers or []}
    return msg


def _header(name, value):
    return {"name": name, "value": value}


class TestExtractGithubMetadata:

    def test_review_requested_reason(self):
        msg = _make_msg(
            subject="[yambay-tech/monorepo] Add feature (PR #1234)",
            headers=[_header("X-GitHub-Reason", "review_requested")],
        )
        meta = extract_github_metadata(msg)
        assert meta["github_reason"] == "review_requested"
        assert meta["github_pr_number"] == 1234

    def test_author_reason(self):
        msg = _make_msg(
            subject="Re: [yambay-tech/monorepo] Fix bug (#567)",
            headers=[_header("X-GitHub-Reason", "author")],
        )
        meta = extract_github_metadata(msg)
        assert meta["github_reason"] == "author"
        assert meta["github_pr_number"] == 567

    def test_push_reason(self):
        msg = _make_msg(
            subject="[yambay-tech/monorepo] Branch push",
            headers=[_header("X-GitHub-Reason", "push")],
        )
        meta = extract_github_metadata(msg)
        assert meta["github_reason"] == "push"

    def test_repo_from_list_id(self):
        msg = _make_msg(
            subject="[yambay-tech/monorepo] Something",
            headers=[_header("List-ID", "<monorepo.yambay-tech.github.com>")],
        )
        meta = extract_github_metadata(msg)
        assert meta["github_repo"] == "yambay-tech/monorepo"

    def test_merged_state_from_subject(self):
        msg = _make_msg(subject="[merged] Fix login flow (#100)")
        meta = extract_github_metadata(msg)
        assert meta["github_pr_state"] == "merged"
        assert meta["github_pr_number"] == 100

    def test_closed_state_from_subject(self):
        msg = _make_msg(subject="[closed] Stale PR (#42)")
        meta = extract_github_metadata(msg)
        assert meta["github_pr_state"] == "closed"
        assert meta["github_pr_number"] == 42

    def test_no_headers_returns_none_values(self):
        msg = _make_msg(subject="Just a normal email")
        meta = extract_github_metadata(msg)
        assert meta["github_reason"] is None
        assert meta["github_repo"] is None
        assert meta["github_pr_number"] is None
        assert meta["github_pr_state"] is None

    def test_pr_number_extracted_from_subject(self):
        msg = _make_msg(subject="Re: [org/repo] Add tests (PR #9999)")
        meta = extract_github_metadata(msg)
        assert meta["github_pr_number"] == 9999

    def test_no_pr_number_when_absent(self):
        msg = _make_msg(subject="General discussion about code")
        meta = extract_github_metadata(msg)
        assert meta["github_pr_number"] is None

    def test_merged_hash_pattern(self):
        msg = _make_msg(subject="Merged #345 into main")
        meta = extract_github_metadata(msg)
        assert meta["github_pr_state"] == "merged"
        assert meta["github_pr_number"] == 345

    def test_closed_hash_pattern(self):
        msg = _make_msg(subject="Closed #678")
        meta = extract_github_metadata(msg)
        assert meta["github_pr_state"] == "closed"
        assert meta["github_pr_number"] == 678
