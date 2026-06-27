#!/usr/bin/env python3
"""Create a draft email in Fastmail. This skill never sends — it only drafts.

The draft lands in your Fastmail Drafts folder. Review and send it yourself
from the Fastmail app or web client.

Usage:
    python3 scripts/create_draft.py \
        --to alice@example.com --cc bob@example.com \
        --subject "Hello" --body "Message text here"

    # Reply to an existing message (threads + quotes original headers):
    python3 scripts/create_draft.py --reply-to <email-id> \
        --body "Thanks, got it."

Multiple --to/--cc/--bcc flags may be given. --from defaults to your
account's primary address. Output is JSON with the new draft's id.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.jmap import JmapClient, die


def _addrs(values):
    return [{"email": v} for v in (values or [])]


def main():
    p = argparse.ArgumentParser(description="Create a Fastmail draft (never sends)")
    p.add_argument("--to", action="append", help="Recipient (repeatable)")
    p.add_argument("--cc", action="append", help="Cc recipient (repeatable)")
    p.add_argument("--bcc", action="append", help="Bcc recipient (repeatable)")
    p.add_argument("--subject", help="Subject line")
    p.add_argument("--body", required=True, help="Plain-text body")
    p.add_argument("--from", dest="from_", help="Sender address (default: account primary)")
    p.add_argument("--reply-to", dest="reply_to",
                   help="Email id to reply to (sets threading + subject)")
    args = p.parse_args()

    client = JmapClient()

    drafts = client.mailbox_by_role("drafts")
    if not drafts:
        die("No Drafts mailbox found on this account.")

    from_email = args.from_ or client.session_data.get("username")
    if not from_email:
        die("Could not determine sender address; pass --from explicitly.")

    subject = args.subject
    to = _addrs(args.to)
    cc = _addrs(args.cc)
    in_reply_to = None
    references = None

    # If replying, pull the original to inherit recipients/subject/threading.
    if args.reply_to:
        resp = client.call([
            ["Email/get", {
                "ids": [args.reply_to],
                "properties": ["subject", "from", "to", "cc", "messageId",
                               "references", "replyTo"],
            }, "g"],
        ])
        orig = client.first_result(resp)["list"]
        if not orig:
            die(f"Reply target not found: {args.reply_to}")
        orig = orig[0]
        if not to:
            reply_targets = orig.get("replyTo") or orig.get("from") or []
            to = [{"email": a["email"]} for a in reply_targets if a.get("email")]
        if subject is None:
            os_ = orig.get("subject") or ""
            subject = os_ if os_.lower().startswith("re:") else f"Re: {os_}"
        orig_msgid = orig.get("messageId") or []
        if orig_msgid:
            in_reply_to = orig_msgid
            references = (orig.get("references") or []) + orig_msgid

    if not to:
        die("No recipients. Provide --to (or --reply-to with a resolvable sender).")

    email_obj = {
        "mailboxIds": {drafts["id"]: True},
        "keywords": {"$draft": True},
        "from": [{"email": from_email}],
        "to": to,
        "subject": subject or "",
        "bodyStructure": {"type": "text/plain", "partId": "body"},
        "bodyValues": {"body": {"value": args.body}},
    }
    if cc:
        email_obj["cc"] = cc
    if args.bcc:
        email_obj["bcc"] = _addrs(args.bcc)
    if in_reply_to:
        email_obj["inReplyTo"] = in_reply_to
    if references:
        email_obj["references"] = references

    resp = client.call([
        ["Email/set", {"create": {"draft": email_obj}}, "c"],
    ])
    result = client.first_result(resp)
    created = result.get("created", {}).get("draft")
    not_created = result.get("notCreated", {})
    if not created:
        die("Draft creation failed", not_created=not_created)

    print(json.dumps({
        "ok": True,
        "draft_id": created["id"],
        "to": [a["email"] for a in to],
        "subject": subject or "",
        "note": "Draft saved to Fastmail Drafts. Review and send it yourself.",
    }, indent=2))


if __name__ == "__main__":
    main()
