#!/usr/bin/env python3
"""Read a single Fastmail email in full, including the body text.

Usage:
    python3 scripts/read_email.py --id <email-id>
    python3 scripts/read_email.py --id <email-id> --html   # prefer HTML body
    python3 scripts/read_email.py --id <email-id> --mark-read

Output is JSON with headers and the decoded body. By default the plain-text
body is returned; pass --html to return the HTML body instead.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.jmap import JmapClient, die

PROPS = [
    "id", "threadId", "subject", "from", "to", "cc", "bcc", "replyTo",
    "receivedAt", "sentAt", "preview", "hasAttachment", "attachments",
    "keywords", "mailboxIds", "messageId", "inReplyTo", "references",
    "textBody", "htmlBody", "bodyValues",
]


def _addr_list(addrs):
    return [{"name": a.get("name"), "email": a.get("email")} for a in (addrs or [])]


def main():
    p = argparse.ArgumentParser(description="Read a Fastmail email")
    p.add_argument("--id", required=True, help="Email id (from search results)")
    p.add_argument("--html", action="store_true", help="Return HTML body instead of text")
    p.add_argument("--mark-read", action="store_true", help="Mark the message as read")
    args = p.parse_args()

    client = JmapClient()
    resp = client.call([
        ["Email/get", {
            "ids": [args.id],
            "properties": PROPS,
            "fetchTextBodyValues": True,
            "fetchHTMLBodyValues": args.html,
        }, "g"],
    ])
    emails = client.first_result(resp)["list"]
    if not emails:
        die(f"Email not found: {args.id}")
    e = emails[0]

    body_values = e.get("bodyValues", {})
    body_parts = e.get("htmlBody") if args.html else e.get("textBody")
    body = "\n".join(
        body_values.get(part["partId"], {}).get("value", "")
        for part in (body_parts or [])
        if part.get("partId") in body_values
    )

    attachments = [{
        "name": a.get("name"),
        "type": a.get("type"),
        "size": a.get("size"),
        "blobId": a.get("blobId"),
    } for a in (e.get("attachments") or [])]

    out = {
        "id": e["id"],
        "subject": e.get("subject"),
        "from": _addr_list(e.get("from")),
        "to": _addr_list(e.get("to")),
        "cc": _addr_list(e.get("cc")),
        "receivedAt": e.get("receivedAt"),
        "messageId": e.get("messageId"),
        "hasAttachment": e.get("hasAttachment", False),
        "attachments": attachments,
        "body_format": "html" if args.html else "text",
        "body": body,
    }

    if args.mark_read:
        client.call([
            ["Email/set", {
                "update": {args.id: {"keywords/$seen": True}},
            }, "s"],
        ])
        out["marked_read"] = True

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
