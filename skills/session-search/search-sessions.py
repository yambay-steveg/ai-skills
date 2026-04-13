#!/usr/bin/env python3
"""Search Claude Code session history for past conversations.

Usage:
    python3 search-sessions.py <query> [options]

Options:
    --deep          Search inside full session transcripts (slower)
    --limit N       Max results to show (default: 10)
    --sort          Sort by 'relevance' (default) or 'date' (most recent first)
    --project PATH  Filter to sessions from a specific project directory
    --days N        Only search sessions from the last N days
    --list-recent N List the N most recent sessions (ignores query)
"""

import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
HISTORY_FILE = CLAUDE_DIR / "history.jsonl"
PROJECTS_DIR = CLAUDE_DIR / "projects"


def copy_to_clipboard(text):
    """Copy text to macOS clipboard using pbcopy."""
    try:
        subprocess.run(["pbcopy"], input=text.encode(), check=True)
        return True
    except Exception:
        return False


def load_history():
    """Load all entries from history.jsonl."""
    entries = []
    if not HISTORY_FILE.exists():
        return entries
    with open(HISTORY_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def get_session_files():
    """Get all session JSONL files across all projects."""
    sessions = {}
    if not PROJECTS_DIR.exists():
        return sessions
    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        for f in project_dir.glob("*.jsonl"):
            session_id = f.stem
            # Skip non-UUID filenames
            if len(session_id) < 30:
                continue
            sessions[session_id] = {
                "path": f,
                "project_dir": project_dir.name,
                "mtime": f.stat().st_mtime,
            }
    return sessions


def extract_first_user_message(session_path):
    """Extract the first user message from a session file."""
    try:
        with open(session_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") == "user" and obj.get("message", {}).get("role") == "user":
                    content = obj["message"].get("content", "")
                    if isinstance(content, str):
                        return content.strip(), obj.get("timestamp")
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                return block["text"].strip(), obj.get("timestamp")
    except Exception:
        pass
    return None, None


def extract_session_summary(session_path, max_messages=50):
    """Extract user messages from a session for search purposes."""
    messages = []
    try:
        with open(session_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") == "user" and obj.get("message", {}).get("role") == "user":
                    content = obj["message"].get("content", "")
                    if isinstance(content, str):
                        messages.append(content.strip())
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                messages.append(block["text"].strip())
                if len(messages) >= max_messages:
                    break
    except Exception:
        pass
    return messages


def deep_search_session(session_path, patterns, max_chars=500000):
    """Search through full session content including assistant messages."""
    matches = []
    chars_read = 0
    try:
        with open(session_path, "r") as f:
            for line in f:
                chars_read += len(line)
                if chars_read > max_chars:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg = obj.get("message", {})
                content = msg.get("content", "")
                text_parts = []

                if isinstance(content, str):
                    text_parts.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text_parts.append(block.get("text", ""))

                full_text = " ".join(text_parts)
                for pattern in patterns:
                    if pattern.search(full_text):
                        # Return a snippet around the match
                        match = pattern.search(full_text)
                        start = max(0, match.start() - 80)
                        end = min(len(full_text), match.end() + 80)
                        snippet = full_text[start:end].replace("\n", " ").strip()
                        role = msg.get("role", obj.get("type", "unknown"))
                        matches.append({"role": role, "snippet": snippet})
                        break
    except Exception:
        pass
    return matches


def format_timestamp(ts):
    """Format a timestamp (ISO string or unix ms) to human-readable in local timezone."""
    if ts is None:
        return "unknown date"
    try:
        if isinstance(ts, str):
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        elif isinstance(ts, (int, float)):
            if ts > 1e12:  # milliseconds
                ts = ts / 1000
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        else:
            return "unknown date"
        # Convert to local timezone
        dt = dt.astimezone()
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "unknown date"


def project_dir_to_path(project_dir_name):
    """Convert encoded project dir name back to path."""
    return project_dir_name.replace("-", "/", 1).replace("-", "/")


def search_history(query, limit=10, project_filter=None, days_filter=None):
    """Search history.jsonl for matching prompts, grouped by session."""
    entries = load_history()
    patterns = [re.compile(re.escape(term), re.IGNORECASE) for term in query.split()]

    # Calculate cutoff timestamp if days filter is set
    cutoff_ts = None
    if days_filter:
        cutoff_ts = (datetime.now(timezone.utc).timestamp() - days_filter * 86400) * 1000

    # Group entries by session
    session_entries = defaultdict(list)
    session_meta = {}

    for entry in entries:
        sid = entry.get("sessionId")
        if not sid:
            continue

        ts = entry.get("timestamp", 0)
        if cutoff_ts and ts < cutoff_ts:
            continue

        project = entry.get("project", "")
        if project_filter and project_filter not in project:
            continue

        session_entries[sid].append(entry)
        if sid not in session_meta:
            session_meta[sid] = {"project": project, "first_ts": ts, "last_ts": ts}
        else:
            session_meta[sid]["last_ts"] = max(session_meta[sid]["last_ts"], ts)

    # Score sessions by keyword match
    scored = []
    for sid, entries_list in session_entries.items():
        all_text = " ".join(e.get("display", "") for e in entries_list).lower()
        score = 0
        matched_terms = 0
        for pattern in patterns:
            matches = pattern.findall(all_text)
            if matches:
                matched_terms += 1
                score += len(matches)

        if matched_terms == len(patterns):  # All terms must match
            # Boost recent sessions
            recency_bonus = session_meta[sid]["last_ts"] / 1e15
            scored.append((sid, score + recency_bonus, entries_list))

    # Sort by score descending (default)
    scored.sort(key=lambda x: x[1], reverse=True)

    return scored[:limit], session_meta


def list_recent_sessions(n=10, project_filter=None):
    """List the N most recent sessions."""
    session_files = get_session_files()

    filtered = []
    for sid, info in session_files.items():
        if project_filter:
            decoded = project_dir_to_path(info["project_dir"])
            if project_filter not in decoded:
                continue
        filtered.append((sid, info))

    # Sort by modification time descending
    filtered.sort(key=lambda x: x[1]["mtime"], reverse=True)

    results = []
    for sid, info in filtered[:n]:
        first_msg, first_ts = extract_first_user_message(info["path"])
        size_kb = info["path"].stat().st_size / 1024
        results.append({
            "session_id": sid,
            "project": project_dir_to_path(info["project_dir"]),
            "date": format_timestamp(info["mtime"]),
            "first_message": (first_msg[:150] + "...") if first_msg and len(first_msg) > 150 else first_msg,
            "size_kb": round(size_kb, 1),
        })

    return results


def _copy_resume_command(results, copy_index, key="session_id"):
    """Copy the resume command for the selected result to clipboard.

    If --copy N is specified, copy that result.
    If there's exactly one result, auto-copy it.
    """
    if not results:
        return

    if copy_index is not None:
        idx = copy_index - 1
        if 0 <= idx < len(results):
            sid = results[idx][key] if isinstance(results[idx], dict) else results[idx]
            cmd = f"claude --resume {sid}"
            if copy_to_clipboard(cmd):
                print(f"  \u2705 Copied to clipboard: {cmd}\n")
            else:
                print(f"  \u26a0\ufe0f  Could not copy to clipboard\n")
        else:
            print(f"  \u26a0\ufe0f  No result #{copy_index} to copy\n")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Search Claude Code sessions")
    parser.add_argument("query", nargs="*", help="Search keywords")
    parser.add_argument("--deep", action="store_true", help="Search full session transcripts")
    parser.add_argument("--limit", type=int, default=10, help="Max results")
    parser.add_argument("--project", type=str, help="Filter by project path")
    parser.add_argument("--days", type=int, help="Only last N days")
    parser.add_argument("--list-recent", type=int, metavar="N", help="List N most recent sessions")
    parser.add_argument("--sort", choices=["relevance", "date"], default="relevance", help="Sort by relevance (default) or date (most recent first)")
    parser.add_argument("--copy", type=int, metavar="N", help="Copy resume command for result N to clipboard")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    # List recent mode
    if args.list_recent:
        results = list_recent_sessions(args.list_recent, args.project)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"\n{'='*80}")
            print(f" {len(results)} Most Recent Sessions")
            print(f"{'='*80}\n")
            for i, r in enumerate(results, 1):
                print(f"  [{i}] Session:  {r['session_id']}")
                print(f"      Date:     {r['date']}")
                print(f"      Project:  {r['project']}")
                print(f"      Size:     {r['size_kb']} KB")
                print(f"      First:    {r['first_message'] or '(empty)'}")
                print(f"      Resume:   claude --resume {r['session_id']}")
                print()
            _copy_resume_command(results, args.copy, key="session_id")
        return

    # Search mode
    if not args.query:
        parser.print_help()
        sys.exit(1)

    query = " ".join(args.query)
    patterns = [re.compile(re.escape(term), re.IGNORECASE) for term in query.split()]

    print(f"\nSearching for: {query}")
    if args.deep:
        print("Mode: deep (searching full transcripts)")
    print()

    # Phase 1: Search history.jsonl
    scored, session_meta = search_history(query, limit=args.limit * 2, project_filter=args.project, days_filter=args.days)

    if not scored and not args.deep:
        print("No matches in prompt history.")
        print("Tip: Use --deep to search inside full session transcripts.\n")
        return

    session_files = get_session_files()

    # Phase 2: For top results, get first message and context
    results = []
    for sid, score, entries_list in scored:
        # Get matching prompts
        matching_prompts = []
        for entry in entries_list:
            text = entry.get("display", "")
            if any(p.search(text) for p in patterns):
                matching_prompts.append(text.strip())

        # Get first user message from the actual session file
        first_msg = None
        first_ts = None
        if sid in session_files:
            first_msg, first_ts = extract_first_user_message(session_files[sid]["path"])
            size_kb = session_files[sid]["path"].stat().st_size / 1024
        else:
            size_kb = 0

        meta = session_meta.get(sid, {})
        results.append({
            "session_id": sid,
            "project": meta.get("project", "unknown"),
            "date": format_timestamp(meta.get("first_ts")),
            "last_active": format_timestamp(meta.get("last_ts")),
            "first_message": (first_msg[:200] + "...") if first_msg and len(first_msg) > 200 else first_msg,
            "matching_prompts": matching_prompts[:5],
            "score": round(score, 2),
            "size_kb": round(size_kb, 1),
        })

    # Phase 3: Deep search if requested and we need more results
    if args.deep:
        already_found = {r["session_id"] for r in results}
        deep_results = []

        # Search all session files
        all_sessions = list(session_files.items())
        all_sessions.sort(key=lambda x: x[1]["mtime"], reverse=True)

        # Limit deep search to recent sessions to keep it fast
        search_limit = min(len(all_sessions), 100)
        print(f"Deep searching {search_limit} most recent sessions...")

        for sid, info in all_sessions[:search_limit]:
            if sid in already_found:
                continue

            if args.project:
                decoded = project_dir_to_path(info["project_dir"])
                if args.project not in decoded:
                    continue

            matches = deep_search_session(info["path"], patterns)
            if matches:
                first_msg, first_ts = extract_first_user_message(info["path"])
                size_kb = info["path"].stat().st_size / 1024
                deep_results.append({
                    "session_id": sid,
                    "project": project_dir_to_path(info["project_dir"]),
                    "date": format_timestamp(first_ts or info["mtime"]),
                    "last_active": format_timestamp(info["mtime"]),
                    "first_message": (first_msg[:200] + "...") if first_msg and len(first_msg) > 200 else first_msg,
                    "matching_prompts": [m["snippet"] for m in matches[:3]],
                    "score": len(matches),
                    "size_kb": round(size_kb, 1),
                    "deep_match": True,
                })

        # Merge and limit
        deep_results.sort(key=lambda x: x["score"], reverse=True)
        results.extend(deep_results)

    results = results[:args.limit]

    # Re-sort by date if requested
    if args.sort == "date":
        results.sort(key=lambda r: r.get("last_active", ""), reverse=True)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"{'='*80}")
        print(f" Found {len(results)} matching session(s)")
        print(f"{'='*80}\n")

        for i, r in enumerate(results, 1):
            deep_tag = " [deep match]" if r.get("deep_match") else ""
            print(f"  [{i}] Session: {r['session_id']}{deep_tag}")
            print(f"      Date:    {r['date']}  (last: {r['last_active']})")
            print(f"      Project: {r['project']}")
            print(f"      Size:    {r['size_kb']} KB")
            if r.get("first_message"):
                print(f"      First:   {r['first_message']}")
            if r.get("matching_prompts"):
                print(f"      Matches:")
                for p in r["matching_prompts"][:3]:
                    truncated = (p[:120] + "...") if len(p) > 120 else p
                    print(f"        - {truncated}")
            print(f"      Resume:  claude --resume {r['session_id']}")
            print()

        _copy_resume_command(results, args.copy, key="session_id")


if __name__ == "__main__":
    main()
