#!/usr/bin/env python3
"""Fetch and parse GitHub notification headers for email messages.

Reads a JSON array of message objects from stdin (must have 'id' field).
Fetches internetMessageHeaders for each and extracts GitHub-specific metadata.

Usage:
    # Pipe from fetch_messages or provide a JSON file
    python fetch_messages.py --folder-name @SaneCC --include-headers | python fetch_github_headers.py
    python fetch_github_headers.py < cc_messages.json

Outputs enriched messages with github_reason, github_repo, github_pr_number, and github_pr_state.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.auth import get_headers, GRAPH_ENDPOINT


def check_pr_state_via_gh(repo: str, pr_number: int) -> str:
    """Check PR state using the gh CLI. Returns 'MERGED', 'CLOSED', 'OPEN', or None."""
    if not repo or not pr_number:
        return None
    try:
        result = subprocess.run(
            ["gh", "pr", "view", str(pr_number), "--repo", repo,
             "--json", "state", "--jq", ".state"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def extract_github_metadata(msg: dict) -> dict:
    """Extract GitHub metadata from a message's headers and subject.

    If internetMessageHeaders are already present in the message, uses those.
    Otherwise returns metadata based on subject line parsing only.
    """
    metadata = {
        "github_reason": None,
        "github_repo": None,
        "github_pr_number": None,
        "github_pr_state": None,
    }

    headers_list = msg.get("internetMessageHeaders", [])
    headers_dict = {h["name"].lower(): h["value"] for h in headers_list}

    # X-GitHub-Reason: review_requested, author, comment, push, ci_activity, mention, etc.
    metadata["github_reason"] = headers_dict.get("x-github-reason")

    # List-ID header often contains repo info: <repo-name.org-name.github.com>
    list_id = headers_dict.get("list-id", "")
    repo_match = re.search(r"<([^.]+)\.([^.]+)\.github\.com>", list_id)
    if repo_match:
        metadata["github_repo"] = f"{repo_match.group(2)}/{repo_match.group(1)}"

    # Subject line parsing for PR number and state
    subject = msg.get("subject", "")

    # PR number: "Re: [org/repo] Title (PR #1234)"
    pr_match = re.search(r"#(\d+)", subject)
    if pr_match:
        metadata["github_pr_number"] = int(pr_match.group(1))

    # State indicators in subject
    subject_lower = subject.lower()
    if "[merged]" in subject_lower or "merged #" in subject_lower:
        metadata["github_pr_state"] = "merged"
    elif "[closed]" in subject_lower or "closed #" in subject_lower:
        metadata["github_pr_state"] = "closed"

    return metadata


def fetch_headers_for_message(api_headers: dict, message_id: str) -> list:
    """Fetch internetMessageHeaders for a single message."""
    url = f"{GRAPH_ENDPOINT}/me/messages/{message_id}"
    params = {"$select": "internetMessageHeaders"}
    resp = requests.get(url, headers=api_headers, params=params)
    resp.raise_for_status()
    return resp.json().get("internetMessageHeaders", [])


def enrich_messages(messages: list, api_headers: dict) -> list:
    """Enrich GitHub messages with metadata.

    If messages already have internetMessageHeaders (from --include-headers),
    uses those directly. Otherwise fetches headers per-message.
    Checks live PR state via gh CLI (cached per repo/PR).
    """
    enriched = []
    total = len(messages)
    pr_state_cache = {}  # (repo, pr_number) -> state

    for i, msg in enumerate(messages):
        # Check if headers already present
        if not msg.get("internetMessageHeaders"):
            print(f"Fetching headers for message {i + 1}/{total}...",
                  file=sys.stderr)
            msg["internetMessageHeaders"] = fetch_headers_for_message(
                api_headers, msg["id"])

        metadata = extract_github_metadata(msg)

        # Check live PR state if we have repo + PR number and no state yet
        repo = metadata.get("github_repo")
        pr_num = metadata.get("github_pr_number")
        if repo and pr_num and not metadata.get("github_pr_state"):
            cache_key = (repo, pr_num)
            if cache_key not in pr_state_cache:
                print(f"Checking PR state: {repo}#{pr_num}...", file=sys.stderr)
                pr_state_cache[cache_key] = check_pr_state_via_gh(repo, pr_num)
            live_state = pr_state_cache[cache_key]
            if live_state:
                metadata["github_pr_state"] = live_state.lower()

        msg.update(metadata)

        # Remove raw headers from output to keep it clean
        msg.pop("internetMessageHeaders", None)
        enriched.append(msg)

    return enriched


def main():
    raw = sys.stdin.read()
    messages = json.loads(raw)

    if not messages:
        print(json.dumps([]))
        return

    # Filter to GitHub emails only
    github_msgs = []
    non_github_msgs = []

    for msg in messages:
        from_email = msg.get("from", {}).get("emailAddress", {}).get("address", "")
        if "github.com" in from_email.lower():
            github_msgs.append(msg)
        else:
            non_github_msgs.append(msg)

    print(f"Found {len(github_msgs)} GitHub emails, {len(non_github_msgs)} non-GitHub emails",
          file=sys.stderr)

    api_headers = get_headers()
    enriched = enrich_messages(github_msgs, api_headers)

    output = {
        "github_messages": enriched,
        "non_github_messages": non_github_msgs,
        "summary": {
            "total": len(messages),
            "github": len(github_msgs),
            "non_github": len(non_github_msgs),
        }
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
