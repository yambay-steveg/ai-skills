---
name: email-tidy
description: >
  Triage SaneBox email folders — tidy @SaneNews, @SaneCC, @SaneBlackHole.
  Use when user says "tidy email", "tidy my email", "clean inbox",
  "triage sanebox", "news tidy", "cc tidy", "blackhole review",
  "email tidy", "review my email folders".
allowed-tools: Bash, Read, Grep
---

# Email Tidy Skill

Triage and clean SaneBox email folders via Microsoft Graph API.

## Setup

### Dependencies

```bash
pip3 install --break-system-packages msal requests python-dotenv
```

### Auth

Uses shared M365 config at `~/.claude/m365/.env` (TENANT_ID, GRAPH_CLIENT_ID).
Token cache at `~/.claude/m365/.token_cache_skills.json`.

Test auth:
```bash
python3 ~/.claude/skills/email-tidy/scripts/test_auth.py
```

### Configuration

User preferences at `~/.claude/skills/email-tidy/config/preferences.json`:
- `github_username` — for filtering GitHub CC emails
- `interest_topics` — topics to flag when scanning BlackHole for rescues
- `known_noise_senders` / `known_good_senders` — learned over time

## Trigger

Use when:
- "tidy email", "tidy my email", "email tidy"
- "news tidy", "tidy news"
- "cc tidy", "tidy cc"
- "blackhole review", "review blackhole"
- "clean inbox", "triage sanebox"
- "summarise my newsletters", "what's in my news"

## Modes

Ask the user which mode to run, or infer from context. If unclear, default to News Tidy.

---

### Mode 1: News Tidy (@SaneNews + @SaneBlackHole)

**Goal:** Keep @SaneNews as a curated reading list. Eject noise to BlackHole. Rescue good content from BlackHole back to News.

**Steps:**

1. Resolve folder IDs:
```bash
python3 ~/.claude/skills/email-tidy/scripts/list_folders.py
```

2. Fetch and analyse @SaneNews:
```bash
python3 ~/.claude/skills/email-tidy/scripts/fetch_messages.py --folder-name "@SaneNews" | \
python3 ~/.claude/skills/email-tidy/scripts/analyse_senders.py
```

3. Fetch and analyse @SaneBlackHole:
```bash
python3 ~/.claude/skills/email-tidy/scripts/fetch_messages.py --folder-name "@SaneBlackHole" | \
python3 ~/.claude/skills/email-tidy/scripts/analyse_senders.py
```

4. Present findings to the user in two tables:

**@SaneNews — Recommend move to BlackHole:**
Show senders with read_rate < 0.10 and total >= 3. Columns: Sender, Total, Unread, Read Rate, Sample Subjects.

**@SaneBlackHole — Possible rescues to News:**
Read `config/preferences.json` interest_topics. Check each BlackHole sender's name and sample subjects against these topics. Use **whole-word matching only** — e.g. "AI" must match as a standalone word, not as a substring of "Awaits" or "Pullman". Flag any genuine matches.

5. **ASK THE USER** which senders to move. Do NOT move anything without explicit approval.

6. On approval, extract the `message_ids` for approved senders and run:
```bash
echo '<JSON array of message IDs>' | \
python3 ~/.claude/skills/email-tidy/scripts/move_messages.py --dest-folder-name "@SaneBlackHole"
```
Or for rescues from BlackHole to News:
```bash
echo '<JSON array of message IDs>' | \
python3 ~/.claude/skills/email-tidy/scripts/move_messages.py --dest-folder-name "@SaneNews"
```

7. After triage, if user wants a news summary: group remaining @SaneNews messages by topic/sender and present a brief summary of recent articles so the user can pick what to read.

---

### Mode 2: CC Tidy (@SaneCC)

**Goal:** Surface actionable items from @SaneCC (especially GitHub notifications). Delete noise.

**Steps:**

1. Fetch @SaneCC messages with headers:
```bash
python3 ~/.claude/skills/email-tidy/scripts/fetch_messages.py --folder-name "@SaneCC" --include-headers
```

2. Pipe through GitHub header enrichment:
```bash
python3 ~/.claude/skills/email-tidy/scripts/fetch_messages.py --folder-name "@SaneCC" --include-headers | \
python3 ~/.claude/skills/email-tidy/scripts/fetch_github_headers.py
```

3. Read `config/preferences.json` for `github_username`.

4. The script now checks live PR state via `gh pr view` (cached per repo/PR).
   **All emails for merged or closed PRs are auto-deleted without confirmation** — the
   full history is in GitHub, there's no value keeping email notifications for closed PRs.

5. For emails on **open PRs**, classify:

**KEEP** (present to user as action items):
- `github_reason` = "review_requested" — someone wants a review
- `github_reason` = "author" — activity on user's own PRs (comments, change requests)
- `github_reason` = "mention" — directly mentioned
- Any email where subject contains the github_username

**BIN** (recommend deletion):
- `github_reason` = "push" — just commit pushes
- `github_reason` = "subscribed" or "comment" on PRs the user did NOT author
- CI/build notification patterns in subject

**REVIEW** (present to user for decision):
- Everything else

6. Present non-GitHub emails from real people separately. NEVER recommend deleting these — just surface them for awareness.

7. Show the classification to the user:
- "Auto-deleted" (closed/merged PRs) with count
- "Action items" (KEEP)
- "Recommended for deletion" (BIN) with counts by category
- "Needs your call" (REVIEW)
- "From people" (non-GitHub)

8. **ASK THE USER** to confirm BIN deletions before proceeding. Closed PR deletions are automatic.

9. On approval:
```bash
echo '<JSON array of message IDs>' | \
python3 ~/.claude/skills/email-tidy/scripts/delete_messages.py
```

---

### Mode 3: BlackHole Review

**Goal:** Quick check that @SaneBlackHole isn't catching anything valuable.

**Steps:**

1. Fetch and analyse @SaneBlackHole (same as News Tidy step 3).

2. Read `config/preferences.json` interest_topics.

3. Check each sender's name and sample subjects against interest topics. Use **whole-word matching only** — avoid false positives from substrings (e.g. "AI" in "Awaits", "LLM" in "Pullman").

4. Present findings:
- If matches found: "These BlackHole senders might interest you: [list]. Want to rescue any to @SaneNews?"
- If no matches: "BlackHole looks clean — no action needed."

5. Only move on explicit approval.

---

## Important Rules

- **NEVER move or delete without explicit user approval.** Present data first, recommendations second, ask for confirmation third.
- **For large backlogs** (first run), process in batches. Present top 20 senders at a time rather than overwhelming the user.
- **For routine runs**, use `--since` flag to limit to recent messages:
  ```bash
  python3 ~/.claude/skills/email-tidy/scripts/fetch_messages.py --folder-name "@SaneNews" --since 2026-03-20
  ```
- **Ask whether this is a first-time catchup or routine tidy** if unclear.
- **Update preferences.json** when the user identifies noise or good senders — add to `known_noise_senders` or `known_good_senders` for future runs.
- All scripts output JSON to stdout and log progress to stderr.
- Moving emails between SaneBox folders trains SaneBox's model, so moves have a lasting effect.
