#!/usr/bin/env python3
"""List Inbox child folders to resolve SaneBox folder IDs.

Outputs JSON with folder displayName, id, unreadItemCount, and totalItemCount.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.auth import get_headers
from lib.graph import get_inbox_id, get_child_folders


def main():
    headers = get_headers()
    inbox_id = get_inbox_id(headers)
    folders = get_child_folders(headers, inbox_id)

    output = []
    for f in folders:
        output.append({
            "displayName": f["displayName"],
            "id": f["id"],
            "unreadItemCount": f.get("unreadItemCount", 0),
            "totalItemCount": f.get("totalItemCount", 0),
        })

    # Sort: @Sane* folders first, then alphabetical
    output.sort(key=lambda x: (not x["displayName"].startswith("@Sane"), x["displayName"]))

    print(json.dumps({"folders": output}, indent=2))


if __name__ == "__main__":
    main()
