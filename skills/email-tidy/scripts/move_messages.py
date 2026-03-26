#!/usr/bin/env python3
"""Move messages to a destination folder.

Reads a JSON array of message IDs from stdin.
Uses Graph batch API for efficiency (20 per batch).

Usage:
    echo '["id1","id2"]' | python move_messages.py --dest-folder-id FOLDER_ID
    echo '["id1","id2"]' | python move_messages.py --dest-folder-name @SaneBlackHole
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.auth import get_headers
from lib.graph import get_folder_id, move_messages


def main():
    parser = argparse.ArgumentParser(description="Move messages to a folder")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dest-folder-id", help="Destination folder ID")
    group.add_argument("--dest-folder-name", help="Destination folder name (e.g. @SaneBlackHole)")
    args = parser.parse_args()

    raw = sys.stdin.read()
    message_ids = json.loads(raw)

    if not message_ids:
        print(json.dumps({"succeeded": 0, "failed": 0, "message": "No messages to move"}))
        return

    headers = get_headers()

    dest_id = args.dest_folder_id
    if args.dest_folder_name:
        dest_id = get_folder_id(headers, args.dest_folder_name)
        print(f"Resolved '{args.dest_folder_name}' to folder ID: {dest_id}",
              file=sys.stderr)

    print(f"Moving {len(message_ids)} messages...", file=sys.stderr)
    result = move_messages(headers, message_ids, dest_id)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
