#!/usr/bin/env python3
"""Verify the Fastmail API token works and show the connected account.

Usage:
    python3 scripts/test_auth.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.jmap import JmapClient, MAIL


def main():
    client = JmapClient()
    accounts = client.session_data.get("accounts", {})
    acc = accounts.get(client.account_id, {})
    out = {
        "ok": True,
        "auth_scheme": client.auth_scheme,
        "account_id": client.account_id,
        "account_name": acc.get("name"),
        "api_url": client.api_url,
        "mail_capable": MAIL in acc.get("accountCapabilities", {}),
        "username": client.session_data.get("username"),
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
