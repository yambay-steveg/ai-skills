#!/usr/bin/env python3
"""Delete messages by ID.

Reads a JSON array of message IDs from stdin.
Uses Graph batch API for efficiency (20 per batch).

Usage:
    echo '["id1","id2"]' | python delete_messages.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.auth import get_headers
from lib.graph import delete_messages


def main():
    raw = sys.stdin.read()
    message_ids = json.loads(raw)

    if not message_ids:
        print(json.dumps({"succeeded": 0, "failed": 0, "message": "No messages to delete"}))
        return

    headers = get_headers()

    print(f"Deleting {len(message_ids)} messages...", file=sys.stderr)
    result = delete_messages(headers, message_ids)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
