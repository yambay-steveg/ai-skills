#!/usr/bin/env python3
"""List Fastmail mailboxes (folders) with message counts.

Usage:
    python3 scripts/list_folders.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.jmap import JmapClient


def main():
    client = JmapClient()
    mailboxes = client.get_mailboxes()
    folders = [
        {
            "id": mb["id"],
            "name": mb.get("name"),
            "role": mb.get("role"),
            "total": mb.get("totalEmails"),
            "unread": mb.get("unreadEmails"),
            "parentId": mb.get("parentId"),
        }
        for mb in sorted(mailboxes, key=lambda m: (m.get("sortOrder", 0), m.get("name", "")))
    ]
    print(json.dumps({"folders": folders}, indent=2))


if __name__ == "__main__":
    main()
