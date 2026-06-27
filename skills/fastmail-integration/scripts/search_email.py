#!/usr/bin/env python3
"""Search Fastmail email and return matching message summaries.

Combines Email/query + Email/get in one JMAP batch via a back-reference, so a
single round-trip returns the headers you need to triage results.

Usage examples:
    python3 scripts/search_email.py --text "invoice"
    python3 scripts/search_email.py --from bp.com --mailbox Inbox --limit 10
    python3 scripts/search_email.py --subject "fleet report" --after 2026-05-01
    python3 scripts/search_email.py --mailbox Inbox --unread

Filters are ANDed together. Output is JSON.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.jmap import JmapClient, die

SUMMARY_PROPS = [
    "id", "threadId", "subject", "from", "to", "receivedAt",
    "preview", "hasAttachment", "keywords", "mailboxIds",
]


def build_filter(client, args):
    conditions = []
    if args.text:
        conditions.append({"text": args.text})
    if args.from_:
        conditions.append({"from": args.from_})
    if args.to:
        conditions.append({"to": args.to})
    if args.subject:
        conditions.append({"subject": args.subject})
    if args.body:
        conditions.append({"body": args.body})
    if args.after:
        conditions.append({"after": _to_utc(args.after)})
    if args.before:
        conditions.append({"before": _to_utc(args.before)})
    if args.unread:
        conditions.append({"notKeyword": "$seen"})
    if args.mailbox:
        mb = client.mailbox_by_role(args.mailbox.lower()) or client.mailbox_by_name(args.mailbox)
        if not mb:
            die(f"Mailbox not found: {args.mailbox}")
        conditions.append({"inMailbox": mb["id"]})

    if not conditions:
        die("No filters given. Provide at least one of --text/--from/--to/"
            "--subject/--body/--mailbox/--after/--before/--unread.")
    if len(conditions) == 1:
        return conditions[0]
    return {"operator": "AND", "conditions": conditions}


def _to_utc(date_str):
    """Accept YYYY-MM-DD or a full RFC3339 timestamp; return RFC3339 UTC."""
    if "T" in date_str:
        return date_str
    return f"{date_str}T00:00:00Z"


def main():
    p = argparse.ArgumentParser(description="Search Fastmail email")
    p.add_argument("--text", help="Free-text search across the message")
    p.add_argument("--from", dest="from_", help="Match sender")
    p.add_argument("--to", help="Match recipient")
    p.add_argument("--subject", help="Match subject")
    p.add_argument("--body", help="Match body text")
    p.add_argument("--mailbox", help="Restrict to a folder (name or role, e.g. Inbox)")
    p.add_argument("--after", help="Only mail received on/after this date (YYYY-MM-DD)")
    p.add_argument("--before", help="Only mail received before this date (YYYY-MM-DD)")
    p.add_argument("--unread", action="store_true", help="Only unread mail")
    p.add_argument("--limit", type=int, default=20, help="Max results (default 20)")
    args = p.parse_args()

    client = JmapClient()
    flt = build_filter(client, args)

    resp = client.call([
        ["Email/query", {
            "filter": flt,
            "sort": [{"property": "receivedAt", "isAscending": False}],
            "limit": args.limit,
            "calculateTotal": True,
        }, "q"],
        ["Email/get", {
            "#ids": {"resultOf": "q", "name": "Email/query", "path": "/ids"},
            "properties": SUMMARY_PROPS,
        }, "g"],
    ])

    query_res = resp["methodResponses"][0][1]
    emails = resp["methodResponses"][1][1]["list"]

    results = [{
        "id": e["id"],
        "subject": e.get("subject"),
        "from": [a.get("email") for a in (e.get("from") or [])],
        "to": [a.get("email") for a in (e.get("to") or [])],
        "receivedAt": e.get("receivedAt"),
        "preview": (e.get("preview") or "").strip()[:200],
        "unread": "$seen" not in (e.get("keywords") or {}),
        "hasAttachment": e.get("hasAttachment", False),
    } for e in emails]

    print(json.dumps({
        "total": query_res.get("total"),
        "returned": len(results),
        "results": results,
    }, indent=2))


if __name__ == "__main__":
    main()
