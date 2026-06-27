"""Unit tests for credential loading / auth-scheme selection (no network)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import jmap


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    # Make sure a real ~/.claude/fastmail/.env isn't loaded during tests.
    monkeypatch.setattr(jmap, "ENV_FILE", Path("/nonexistent/.env"))
    for var in ("FASTMAIL_API_TOKEN", "FASTMAIL_USER", "FASTMAIL_APP_PASSWORD"):
        monkeypatch.delenv(var, raising=False)


def test_bearer_token(monkeypatch):
    monkeypatch.setenv("FASTMAIL_API_TOKEN", "fmu1-abc")
    assert jmap.load_credentials() == ("bearer", "fmu1-abc")


def test_basic_auth(monkeypatch):
    monkeypatch.setenv("FASTMAIL_USER", "steve@godding.net")
    monkeypatch.setenv("FASTMAIL_APP_PASSWORD", "secret")
    assert jmap.load_credentials() == ("basic", ("steve@godding.net", "secret"))


def test_token_wins_over_basic(monkeypatch):
    monkeypatch.setenv("FASTMAIL_API_TOKEN", "fmu1-abc")
    monkeypatch.setenv("FASTMAIL_USER", "steve@godding.net")
    monkeypatch.setenv("FASTMAIL_APP_PASSWORD", "secret")
    assert jmap.load_credentials() == ("bearer", "fmu1-abc")


def test_no_credentials_exits():
    with pytest.raises(SystemExit):
        jmap.load_credentials()
