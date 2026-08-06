"""Contract tests for `search-sessions.py --json`.

These exist because the board (session-card-board) consumes this script the way it
consumes `cardctl`: spawn it, parse stdout as JSON. That only works if stdout carries
*nothing but* the payload — progress chatter used to be printed there too, which made
`--json` unparseable, and a no-match search printed nothing at all.

Run the script as a subprocess (not an import) so the assertions are about the real
stdout/stderr split a caller sees. `Path.home()` honours `HOME` on POSIX, so each test
points the script at a synthetic `~/.claude`.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "search-sessions.py"


def write_history(home, entries):
    """Create `$HOME/.claude/history.jsonl` (plus an empty projects dir) from entries."""
    claude = home / ".claude"
    (claude / "projects").mkdir(parents=True, exist_ok=True)
    (claude / "history.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in entries)
    )


def entry(sid, display, project="/tmp/proj", ts=1_750_000_000_000):
    return {"sessionId": sid, "display": display, "project": project, "timestamp": ts}


def run(home, *args):
    env = {**os.environ, "HOME": str(home)}
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, env=env, timeout=60,
    )


@pytest.fixture
def home(tmp_path):
    write_history(tmp_path, [
        entry("aaaaaaaa-1111-2222-3333-444444444444", "fix the widget exporter"),
        entry("bbbbbbbb-1111-2222-3333-444444444444", "unrelated grocery list"),
    ])
    return tmp_path


def test_search_json_stdout_is_parseable(home):
    """The regression: stdout used to carry a 'Searching for: …' preamble before the JSON."""
    r = run(home, "widget", "--json")
    assert r.returncode == 0
    rows = json.loads(r.stdout)                     # would raise on any preamble
    assert [x["session_id"] for x in rows] == ["aaaaaaaa-1111-2222-3333-444444444444"]


def test_search_progress_goes_to_stderr_not_stdout(home):
    r = run(home, "widget", "--json")
    assert "Searching for" in r.stderr             # humans still see it
    assert "Searching for" not in r.stdout         # machines don't


def test_no_matches_emits_empty_array_not_empty_stdout(home):
    """'No results' is a result: a caller must be able to parse every outcome."""
    r = run(home, "zzzznomatchzzzz", "--json")
    assert r.returncode == 0
    assert json.loads(r.stdout) == []


def test_no_matches_without_json_stays_human(home):
    r = run(home, "zzzznomatchzzzz")
    assert r.returncode == 0
    assert r.stdout.strip() == ""                  # human text is progress → stderr
    assert "No matches in prompt history." in r.stderr


def test_list_recent_json_is_parseable(home):
    r = run(home, "--list-recent", "5", "--json")
    assert r.returncode == 0
    assert isinstance(json.loads(r.stdout), list)


def test_project_filter_scopes_results(home):
    """The board's per-card query: sessions under one of the card's paths."""
    write_history(home, [
        entry("cccccccc-1111-2222-3333-444444444444", "widget work", project="/tmp/other"),
        entry("dddddddd-1111-2222-3333-444444444444", "widget work", project="/tmp/proj"),
    ])
    rows = json.loads(run(home, "widget", "--json", "--project", "/tmp/proj").stdout)
    assert [x["session_id"] for x in rows] == ["dddddddd-1111-2222-3333-444444444444"]


def test_human_mode_still_prints_results_to_stdout(home):
    """Only *progress* moved to stderr — the result table is still stdout."""
    r = run(home, "widget")
    assert "aaaaaaaa-1111-2222-3333-444444444444" in r.stdout
    assert "Found 1 matching session(s)" in r.stdout
