"""Tests for the template skill script."""
import subprocess
import sys


def test_main_runs():
    result = subprocess.run(
        [sys.executable, "skills/_template/scripts/main.py", "--arg", "hello"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "hello" in result.stdout
