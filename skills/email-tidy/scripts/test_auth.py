#!/usr/bin/env python3
"""Verify M365 authentication works for the email-tidy skill."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.auth import get_headers, GRAPH_ENDPOINT

import requests


def main():
    headers = get_headers()
    resp = requests.get(f"{GRAPH_ENDPOINT}/me", headers=headers)
    resp.raise_for_status()
    user = resp.json()
    print(json.dumps({
        "status": "ok",
        "user": user.get("displayName"),
        "email": user.get("mail"),
    }, indent=2))


if __name__ == "__main__":
    main()
