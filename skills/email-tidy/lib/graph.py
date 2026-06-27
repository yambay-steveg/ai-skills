#!/usr/bin/env python3
"""Microsoft Graph API helpers for email operations.

Provides folder resolution, paginated message listing, and batch operations.
"""

import json
import sys
import time

import requests

from .auth import GRAPH_ENDPOINT

BATCH_ENDPOINT = f"{GRAPH_ENDPOINT}/$batch"
MAX_BATCH_SIZE = 20


def get_inbox_id(headers: dict) -> str:
    """Get the Inbox folder ID."""
    url = f"{GRAPH_ENDPOINT}/me/mailFolders/Inbox"
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()["id"]


def get_child_folders(headers: dict, parent_folder_id: str) -> list:
    """List child folders of a mail folder."""
    url = f"{GRAPH_ENDPOINT}/me/mailFolders/{parent_folder_id}/childFolders"
    params = {"$top": 100}
    folders = []

    while url:
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        folders.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
        params = None  # nextLink includes params

    return folders


def get_folder_id(headers: dict, folder_name: str, parent_folder_id: str = None) -> str:
    """Resolve a SaneBox folder name (e.g. '@SaneNews') to its ID.

    Searches child folders of the given parent (defaults to Inbox).
    """
    if parent_folder_id is None:
        parent_folder_id = get_inbox_id(headers)

    folders = get_child_folders(headers, parent_folder_id)

    for folder in folders:
        if folder["displayName"] == folder_name:
            return folder["id"]

    available = [f["displayName"] for f in folders]
    raise ValueError(f"Folder '{folder_name}' not found. Available: {available}")


def list_messages(headers: dict, folder_id: str, since: str = None,
                  select: str = None, include_headers: bool = False,
                  top: int = 100) -> list:
    """Fetch all messages from a folder with pagination.

    Args:
        folder_id: The mail folder ID.
        since: Optional ISO date string (YYYY-MM-DD) to filter messages received on or after.
        select: Comma-separated fields to return. Defaults to common fields.
        include_headers: If True, includes internetMessageHeaders in response.
        top: Page size (max 1000, default 100).

    Returns:
        List of message dicts.
    """
    if select is None:
        fields = ["id", "subject", "from", "receivedDateTime", "isRead"]
        if include_headers:
            fields.append("internetMessageHeaders")
        select = ",".join(fields)

    url = f"{GRAPH_ENDPOINT}/me/mailFolders/{folder_id}/messages"
    params = {
        "$select": select,
        "$top": min(top, 1000),
        "$orderby": "receivedDateTime desc",
    }

    if since:
        params["$filter"] = f"receivedDateTime ge {since}T00:00:00Z"

    messages = []
    page = 0

    while url:
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("value", [])
        messages.extend(batch)
        page += 1
        print(f"Fetched page {page}: {len(batch)} messages (total: {len(messages)})",
              file=sys.stderr)
        url = data.get("@odata.nextLink")
        params = None  # nextLink includes params

    return messages


def move_messages(headers: dict, message_ids: list, destination_folder_id: str) -> dict:
    """Move messages to a destination folder using batch API.

    Returns dict with 'succeeded' and 'failed' counts.
    """
    return _batch_operation(headers, message_ids, "move", destination_folder_id)


def delete_messages(headers: dict, message_ids: list) -> dict:
    """Delete messages using batch API.

    Returns dict with 'succeeded' and 'failed' counts.
    """
    return _batch_operation(headers, message_ids, "delete")


def _batch_operation(headers: dict, message_ids: list, operation: str,
                     destination_folder_id: str = None) -> dict:
    """Execute a batch move or delete operation.

    Chunks into groups of MAX_BATCH_SIZE (20) per Graph API limits.
    Handles 429 rate limiting with retry.
    """
    succeeded = 0
    failed = 0
    errors = []

    for chunk_start in range(0, len(message_ids), MAX_BATCH_SIZE):
        chunk = message_ids[chunk_start:chunk_start + MAX_BATCH_SIZE]
        batch_requests = []

        for i, msg_id in enumerate(chunk):
            if operation == "move":
                batch_requests.append({
                    "id": str(i),
                    "method": "POST",
                    "url": f"/me/messages/{msg_id}/move",
                    "headers": {"Content-Type": "application/json"},
                    "body": {"destinationId": destination_folder_id},
                })
            elif operation == "delete":
                batch_requests.append({
                    "id": str(i),
                    "method": "DELETE",
                    "url": f"/me/messages/{msg_id}",
                })

        result = _send_batch_with_retry(headers, batch_requests)

        for resp in result.get("responses", []):
            status = resp.get("status", 0)
            if 200 <= status < 300:
                succeeded += 1
            else:
                failed += 1
                errors.append({
                    "id": resp.get("id"),
                    "status": status,
                    "body": resp.get("body", {}),
                })

        print(f"Batch {chunk_start // MAX_BATCH_SIZE + 1}: "
              f"{succeeded} succeeded, {failed} failed",
              file=sys.stderr)

    result = {"succeeded": succeeded, "failed": failed}
    if errors:
        result["errors"] = errors
    return result


def _send_batch_with_retry(headers: dict, batch_requests: list,
                           max_retries: int = 3) -> dict:
    """Send a batch request with retry on 429."""
    batch_headers = {
        "Authorization": headers["Authorization"],
        "Content-Type": "application/json",
    }
    payload = {"requests": batch_requests}

    for attempt in range(max_retries):
        resp = requests.post(BATCH_ENDPOINT, headers=batch_headers,
                             json=payload)

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 5))
            print(f"Rate limited, waiting {retry_after}s (attempt {attempt + 1})",
                  file=sys.stderr)
            time.sleep(retry_after)
            continue

        resp.raise_for_status()
        return resp.json()

    resp.raise_for_status()
    return resp.json()
