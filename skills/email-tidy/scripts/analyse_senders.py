#!/usr/bin/env python3
"""Analyse messages grouped by sender.

Reads JSON message array from stdin (output of fetch_messages.py).
Outputs sender statistics: total, unread, read rate, sample subjects, message IDs.

Usage:
    python fetch_messages.py --folder-name @SaneNews | python analyse_senders.py
    python analyse_senders.py < messages.json
"""

import json
import sys
from collections import defaultdict


def analyse(messages: list) -> dict:
    """Group messages by sender and compute statistics."""
    senders = defaultdict(lambda: {
        "email": "",
        "name": "",
        "total": 0,
        "unread": 0,
        "read": 0,
        "message_ids": [],
        "subjects": [],
        "earliest": None,
        "latest": None,
    })

    for msg in messages:
        from_field = msg.get("from", {}).get("emailAddress", {})
        email = from_field.get("address", "unknown").lower()
        name = from_field.get("name", "")
        received = msg.get("receivedDateTime", "")
        is_read = msg.get("isRead", False)
        subject = msg.get("subject", "(no subject)")

        sender = senders[email]
        sender["email"] = email
        sender["name"] = name
        sender["total"] += 1
        if is_read:
            sender["read"] += 1
        else:
            sender["unread"] += 1
        sender["message_ids"].append(msg["id"])

        # Keep up to 3 unique subject patterns
        if len(sender["subjects"]) < 3 and subject not in sender["subjects"]:
            sender["subjects"].append(subject)

        if received:
            if sender["earliest"] is None or received < sender["earliest"]:
                sender["earliest"] = received
            if sender["latest"] is None or received > sender["latest"]:
                sender["latest"] = received

    # Compute read rates and sort by read rate ascending (worst-read first)
    result = []
    for email, data in senders.items():
        data["read_rate"] = round(data["read"] / data["total"], 2) if data["total"] > 0 else 0
        result.append(data)

    result.sort(key=lambda x: (x["read_rate"], -x["total"]))

    return {
        "senders": result,
        "total_messages": len(messages),
        "total_senders": len(result),
    }


def main():
    raw = sys.stdin.read()
    messages = json.loads(raw)
    output = analyse(messages)
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
