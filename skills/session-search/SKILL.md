---
skill: session-search
version: 1.3.0
updated: 2026-03-23
trigger: "find session", "search session", "previous session", "resume session", "find conversation", "past conversation", "session about"
---

# Session Search Skill

Search and find previous Claude Code sessions by keywords, topic, or recency.

## When to Use

Trigger this skill when the user asks to:
- Find a previous/past session or conversation
- Resume a session about a specific topic
- Search for something discussed in an earlier session
- List recent sessions

## How It Works

Claude Code stores session data in `~/.claude/`:
- **`history.jsonl`** — lightweight index of every user prompt with session ID and timestamp
- **`projects/<encoded-path>/<sessionId>.jsonl`** — full session transcripts (JSONL)

The search script (`search-sessions.py`) searches these sources.

## Usage

### Quick Search (history index only — fast)
```bash
python3 ~/.claude/skills/session-search/search-sessions.py <keywords>
```

### Deep Search (full session transcripts — slower)
```bash
python3 ~/.claude/skills/session-search/search-sessions.py <keywords> --deep
```

### List Recent Sessions
```bash
python3 ~/.claude/skills/session-search/search-sessions.py --list-recent 10
```

### Options
| Flag | Description |
|------|-------------|
| `--deep` | Search inside full session transcripts (not just prompts) |
| `--limit N` | Max results (default: 10) |
| `--sort` | Sort by `relevance` (default) or `date` (most recent first) |
| `--project PATH` | Filter to sessions from a specific project path |
| `--days N` | Only search sessions from the last N days |
| `--list-recent N` | List N most recent sessions (ignores query) |
| `--copy N` | Copy resume command for result #N to clipboard |
| `--json` | Output as JSON for programmatic use |

## Workflow

1. **Run the search script** with the user's keywords
2. **Present results** as a table: date, first message, session ID
3. **Copy the most relevant result** using `--copy N` (always do this — don't leave it to the user)
4. **If user wants to resume**: they can paste the resume command, OR read the session JSONL directly to extract context into the current session

### Reading a Session Transcript

If the user wants to review session content without leaving the current session:
```bash
# Extract all user messages from a session
python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    for line in f:
        obj = json.loads(line)
        if obj.get('type') == 'user':
            msg = obj.get('message', {}).get('content', '')
            if isinstance(msg, str) and msg.strip():
                print(f\"USER: {msg.strip()[:200]}\")
            elif isinstance(msg, list):
                for b in msg:
                    if isinstance(b, dict) and b.get('type') == 'text':
                        print(f\"USER: {b['text'].strip()[:200]}\")
" ~/.claude/projects/-Users-leon-claude-code/<sessionId>.jsonl
```

### Session File Locations

Sessions are stored by project directory. The directory name is the absolute path with `/` replaced by `-`:
- `/Users/leon/claude-code` → `~/.claude/projects/-Users-leon-claude-code/`
- `/Users/leon` → `~/.claude/projects/-Users-leon/`

## Important Notes

- History search is fast (searches prompt text in `history.jsonl`)
- Deep search reads actual session files — limit to recent sessions if speed matters
- Session IDs are UUIDs (e.g., `27560806-71b7-4593-93ba-a03f355346ae`)
- To resume: user runs `claude --resume <session-id>` in a new terminal
- Within current session, you can READ session files to extract relevant context
