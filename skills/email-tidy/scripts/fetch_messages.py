#!/usr/bin/env python3
"""Fetch messages from a mail folder with pagination.

Usage:
    python fetch_messages.py --folder-id FOLDER_ID [--since 2026-03-20] [--include-headers]
    python fetch_messages.py --folder-name @SaneNews [--since 2026-03-20] [--include-headers]

Outputs JSON array of messages to stdout. Progress logged to stderr.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.auth import get_headers
from lib.graph import get_folder_id, list_messages


def main():
    parser = argparse.ArgumentParser(description="Fetch messages from a mail folder")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--folder-id", help="Mail folder ID")
    group.add_argument("--folder-name", help="SaneBox folder name (e.g. @SaneNews)")
    parser.add_argument("--since", help="Only fetch messages received on or after this date (YYYY-MM-DD)")
    parser.add_argument("--include-headers", action="store_true",
                        help="Include internetMessageHeaders (needed for GitHub emails)")
    parser.add_argument("--top", type=int, default=100, help="Page size (default: 100)")
    args = parser.parse_args()

    headers = get_headers()

    folder_id = args.folder_id
    if args.folder_name:
        folder_id = get_folder_id(headers, args.folder_name)
        print(f"Resolved '{args.folder_name}' to folder ID: {folder_id}", file=sys.stderr)

    messages = list_messages(
        headers,
        folder_id,
        since=args.since,
        include_headers=args.include_headers,
        top=args.top,
    )

    print(json.dumps(messages, indent=2))
    print(f"Total: {len(messages)} messages", file=sys.stderr)


if __name__ == "__main__":
    main()
