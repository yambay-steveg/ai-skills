"""Contract tests for the SessionStart hook's timezone block.

The hook is deployed to `~/bin` by `cardctl deploy` (HOOK_SRC), so it's part of the
session-card system and lives in this suite. It's a zsh script, so these drive it as a
subprocess and assert on the JSON it emits.

Determinism without freezing the clock: the travel window is declared by environment
variables, so "during a trip" is a far-future `TRAVEL_UNTIL` and "trip over" is a past
one. Expected zone labels are computed with the same `date` the hook uses rather than
hardcoded, so BST/GMT and AWST all stay correct year-round.
"""
import json
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / "bin" / "session-start-hook.sh"
LONDON = "Europe/London"
PERTH = "Australia/Perth"


def run_hook(env=None, cwd_payload=None):
    """Run the hook with an optional stdin payload; return its additionalContext string."""
    res = subprocess.run(
        ["zsh", str(HOOK)],
        input=json.dumps(cwd_payload or {}),
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(Path.home()), **(env or {})},
        timeout=30,
    )
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)["hookSpecificOutput"]["additionalContext"]


def zone_label(tz):
    """The %Z label `date` gives for a zone right now (BST vs GMT, AWST vs AWDT)."""
    return subprocess.run(["date", "+%Z"], capture_output=True, text=True,
                          env={"TZ": tz, "PATH": "/usr/bin:/bin"}).stdout.strip()


def test_defaults_to_home_timezone_when_no_trip_declared():
    out = run_hook()
    assert zone_label(PERTH) in out
    assert "travelling" not in out


def test_travel_window_open_uses_the_travel_zone():
    out = run_hook({"TRAVEL_TZ": LONDON, "TRAVEL_UNTIL": "2099-01-01"})
    assert zone_label(LONDON) in out
    assert "travelling" in out and "2099-01-01" in out


def test_travel_window_expired_reverts_home_by_itself():
    """The point of the dated window: a forgotten edit can't strand the wrong zone."""
    out = run_hook({"TRAVEL_TZ": LONDON, "TRAVEL_UNTIL": "2020-01-01"})
    assert zone_label(PERTH) in out
    assert "travelling" not in out


def test_travel_until_is_inclusive():
    """Last day away still reports the travel zone (it's a date you're still there)."""
    today_there = subprocess.run(["date", "+%Y-%m-%d"], capture_output=True, text=True,
                                 env={"TZ": LONDON, "PATH": "/usr/bin:/bin"}).stdout.strip()
    out = run_hook({"TRAVEL_TZ": LONDON, "TRAVEL_UNTIL": today_there})
    assert "travelling" in out


@pytest.mark.parametrize("env", [
    {"TRAVEL_TZ": LONDON},                      # zone without an end date
    {"TRAVEL_UNTIL": "2099-01-01"},             # end date without a zone
    {"TRAVEL_TZ": "", "TRAVEL_UNTIL": ""},      # both blank
])
def test_half_declared_trip_is_ignored_not_guessed(env):
    """A partial declaration falls back home rather than inventing a zone."""
    out = run_hook(env)
    assert zone_label(PERTH) in out
    assert "travelling" not in out


def test_home_tz_is_overridable():
    out = run_hook({"HOME_TZ": LONDON})
    assert zone_label(LONDON) in out
    assert "travelling" not in out


def test_emits_wellformed_hook_json_with_no_cwd():
    """No cwd → time context only, still valid SessionStart output."""
    res = subprocess.run(["zsh", str(HOOK)], input="", capture_output=True, text=True,
                         env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(Path.home())},
                         timeout=30)
    assert res.returncode == 0
    payload = json.loads(res.stdout)
    assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "Current time:" in payload["hookSpecificOutput"]["additionalContext"]
