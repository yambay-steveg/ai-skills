---
name: fastmail-integration
description: >
  Read, search, and draft email from Steve's personal Fastmail account
  (steve@godding.net) via the JMAP API. Use when the user says "check my
  Fastmail", "search my personal email", "any email from X", "read that
  email", "draft a reply", "draft an email to X", or refers to godding.net /
  personal (non-Yambay) mail. For Yambay/M365 work email use the m365 email
  skill instead.
allowed-tools: Bash, Read, Write, Edit
---

# Fastmail Integration

## Overview

Connects to Steve's personal email on **Fastmail** (`steve@godding.net`) using
the **JMAP API** with a Bearer API token. Supports:

- **Search** mail by sender, recipient, subject, body, free text, folder, date
- **Read** a single message in full (headers + body + attachment list)
- **List** folders (mailboxes) with counts
- **Draft** new emails and replies

**Sending is intentionally not supported.** Per Steve's choice, this skill only
ever creates **drafts** in Fastmail. He reviews and sends them himself from the
Fastmail app/web client. Do not attempt to add a send step.

## Trigger

Use when the user wants to work with **personal** email:
- "check my Fastmail", "any new personal email", "search my godding.net mail"
- "any email from <person/company>", "find the email about <topic>"
- "read that email", "what does it say"
- "draft a reply to that", "draft an email to <someone>"

Do NOT use when:
- The user means **Yambay/work** email — use the `m365` email skill (Outlook).
- The user wants to actually *send* — this skill drafts only; tell them to send
  from Fastmail, or that sending isn't wired up.

## Setup (one-time)

Credentials live in `~/.claude/fastmail/.env` (a secret — never in the repo).
Use **either** auth method:

**Option A — share the invoice-harvester app password (least setup):**
```
FASTMAIL_USER=steve@godding.net
FASTMAIL_APP_PASSWORD=<same app password invoice-harvester uses>
```
The app password must allow **JMAP** access — an "IMAP only" password is
rejected by the JMAP endpoint. If `test_auth.py` returns 401, create a new app
password in Fastmail (Settings → Privacy & Security → App passwords) that allows
JMAP, and share it between both apps.

**Option B — dedicated API token:**
```
FASTMAIL_API_TOKEN=fmu1-xxxxxxxx...
```
Create in Fastmail: Settings → Privacy & Security → Manage API tokens, scope
**Mail (read & write)**.

If both are present, the API token wins. Verify with:
`python3 ~/.claude/skills/fastmail-integration/scripts/test_auth.py`

## Instructions

All scripts print JSON. Run them from the skill directory (or use absolute
paths). When installed, that is `~/.claude/skills/fastmail-integration/`; in the
repo it is `skills/fastmail-integration/`.

### Search

```bash
python3 scripts/search_email.py --from bp.com --mailbox Inbox --limit 10
python3 scripts/search_email.py --text "invoice" --after 2026-05-01
python3 scripts/search_email.py --subject "fleet report"
python3 scripts/search_email.py --mailbox Inbox --unread
```
Filters are ANDed. Each result includes an `id` — use it to read the full
message. Present results as a concise list (sender, subject, date, preview).

### Read

```bash
python3 scripts/read_email.py --id <email-id>
python3 scripts/read_email.py --id <email-id> --html        # HTML body
python3 scripts/read_email.py --id <email-id> --mark-read   # also mark read
```

### List folders

```bash
python3 scripts/list_folders.py
```

### Draft (never sends)

```bash
python3 scripts/create_draft.py --to alice@example.com \
    --subject "Hello" --body "Message text."

# Reply (inherits recipients/subject/threading from the original):
python3 scripts/create_draft.py --reply-to <email-id> --body "Thanks!"
```
`--to`, `--cc`, `--bcc` are repeatable. After creating a draft, tell Steve it's
in his Fastmail Drafts folder for review and sending — do not claim it was sent.

### Working pattern

1. Search to find candidate messages → show Steve the shortlist.
2. Read the chosen message by `id` for full content.
3. If drafting a reply, draft from the original's `id` so threading is correct.
4. Show the drafted text and confirm it's saved to Drafts for him to send.

## Configuration

- `~/.claude/fastmail/.env` — credentials (secret). Either `FASTMAIL_API_TOKEN`,
  or `FASTMAIL_USER` + `FASTMAIL_APP_PASSWORD`. Token wins if both present.
- JMAP session endpoint and capabilities are handled in `lib/jmap.py`.

## Dependencies

- Python 3 with: `requests`, `python-dotenv`
  (`pip install --break-system-packages requests python-dotenv` on macOS).

## Notes

- Account context: `steve@godding.net`, hosted on Fastmail (Individual
  Standard). See the personal-vault card `apple-family-email-setup` for the full
  email estate and mail-flow background.
- Email forwarded from `steve@godding.com.au` (Google Workspace) lands in this
  same inbox.
