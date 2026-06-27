# Fastmail integration
<!-- card: /Users/steve/Source/work/yambay-steveg/work-knowledge/Cards/fastmail-integration.md -->

**Started:** 2026-06-27 (AWST)

A Claude Code skill that connects to Steve's personal Fastmail account
(`steve@godding.net`) over the **JMAP API** to **search, read, list, and draft**
email — all from within a Claude Code session.

**Draft-only by design.** The skill never sends. It creates drafts in Fastmail
for review and manual sending. This is enforced in two places: there is no send
code path, *and* the API token carries no `submission` scope, so sending is
impossible at the credential level.

This README is the complete build/deploy/maintain reference. `SKILL.md` is the
Claude-facing runtime spec (when to trigger, which command to run); this file is
for a human (or AI) building, deploying, or extending the skill.

---

## Architecture

```
Claude Code  ──runs──▶  scripts/*.py  ──use──▶  lib/jmap.py  ──HTTPS/JSON──▶  api.fastmail.com (JMAP)
                            │                        │
                       argparse CLI            session discovery + auth
                       JSON stdout             batched method calls
```

- **Transport:** JMAP (RFC 8620 core + RFC 8621 mail). Fastmail is the reference
  JMAP implementation. One HTTPS endpoint, JSON request/response, no per-protocol
  connection juggling (unlike IMAP/SMTP).
- **One round-trip where possible:** `search_email.py` issues `Email/query` +
  `Email/get` in a single batch using a JMAP back-reference (`#ids`), so a search
  returns message headers in one request.
- **Every script prints JSON to stdout** and errors as JSON to stderr, so Claude
  can parse results deterministically.

### Files

| Path | Responsibility |
|------|----------------|
| `SKILL.md` | Skill definition — triggers, setup, usage. What Claude reads. |
| `lib/jmap.py` | JMAP client: credential loading, session discovery (`apiUrl` + `accountId`), batched `call()`, mailbox helpers (`by_role`/`by_name`). |
| `scripts/test_auth.py` | Verify credentials; print account + auth scheme. |
| `scripts/list_folders.py` | `Mailbox/get` → folders with total/unread counts. |
| `scripts/search_email.py` | `Email/query` + `Email/get` → message summaries. ANDs filters. |
| `scripts/read_email.py` | `Email/get` → full message (headers, body text/HTML, attachments); optional `--mark-read`. |
| `scripts/create_draft.py` | `Email/set create` into Drafts. New mail or `--reply-to` (inherits threading/recipients/subject). Never sends. |
| `tests/` | Offline unit tests (no network) for filter building + auth-scheme selection. |

---

## Authentication

The JMAP endpoint accepts either credential type; `lib/jmap.py` supports both
and prefers the token if both are present. Config lives in
`~/.claude/fastmail/.env` (outside the repo — never committed).

| Method | Env vars | Created in Fastmail | Notes |
|--------|----------|---------------------|-------|
| **API token** (used in prod) | `FASTMAIL_API_TOKEN` | Settings → Privacy & Security → Manage API tokens | Bearer auth. Fine-grained scopes. **This is what the skill runs on.** Token named `claude-code`, scope **Mail (read & write)**, no submission. |
| App password (fallback) | `FASTMAIL_USER` + `FASTMAIL_APP_PASSWORD` | Settings → Privacy & Security → App passwords | HTTP Basic auth. Must allow **JMAP** access — an "IMAP only" app password is rejected by the JMAP endpoint (returns 401). |

**Why a token over an app password:** least privilege. The token grants Mail
read/write only — no SMTP/send, no Contacts, no CalDAV — and is independently
revocable without touching any other integration. The sibling `invoice-harvester`
app uses its own separate IMAP-only app password; each consumer gets its own
minimally-scoped credential named after itself.

**Why not read-only:** creating a draft (and `--mark-read`) is a write. Read-only
tokens block both. Send is prevented by omitting the submission scope, not by
read-only.

---

## Dependencies

- Python 3 with `requests` and `python-dotenv`:
  ```bash
  pip install --break-system-packages requests python-dotenv   # macOS managed Python (PEP 668)
  ```

---

## Build / deploy

1. **Configure credentials** (one-time): create the API token (see above) and
   write it to `~/.claude/fastmail/.env`:
   ```
   FASTMAIL_API_TOKEN=fmu1-xxxxxxxx...
   ```
2. **Verify auth:**
   ```bash
   python3 scripts/test_auth.py
   # → {"ok": true, "auth_scheme": "bearer", "account_name": "steve@godding.net", ...}
   ```
3. **Run the tests:**
   ```bash
   python3 -m pytest tests/ -q
   ```
4. **Deploy** to the live skills directory (source of truth stays in this repo;
   this copies a runtime copy Claude loads at session start):
   ```bash
   ./install.sh fastmail-integration       # from repo root
   ```
5. **Restart the Claude Code session** — skills only load at session start.

---

## Usage (CLI)

All scripts print JSON. Run from the skill directory.

```bash
# Search (filters are ANDed; each result has an id)
python3 scripts/search_email.py --from bp.com --mailbox Inbox --limit 10
python3 scripts/search_email.py --text "invoice" --after 2026-05-01
python3 scripts/search_email.py --mailbox Inbox --unread

# Read one message in full
python3 scripts/read_email.py --id <email-id>
python3 scripts/read_email.py --id <email-id> --html --mark-read

# Folders
python3 scripts/list_folders.py

# Draft (never sends — lands in Fastmail Drafts)
python3 scripts/create_draft.py --to a@example.com --subject "Hi" --body "Text."
python3 scripts/create_draft.py --reply-to <email-id> --body "Thanks!"
```

---

## Extending

- **Enable sending (deliberate, future):** add the `submission` scope to the
  token, then a `send_email.py` that calls `EmailSubmission/set` referencing a
  created draft. Gate it behind explicit in-chat confirmation. This was
  intentionally left out — see the `apple-family-email-setup` decision (draft-only).
- **More search filters:** extend `build_filter()` in `search_email.py`; JMAP
  `Email/query` filter conditions are listed in RFC 8621.
- **Contacts / calendar:** add the relevant capability URN to the `using` list in
  `lib/jmap.py` and the matching scope to the token.

---

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `No Fastmail credentials found` | `~/.claude/fastmail/.env` missing or empty. Add token or user+app-password. |
| `Fastmail rejected the credentials (401)` | Bad/expired token, or an app password scoped IMAP-only (must allow JMAP). |
| Skill doesn't trigger in chat | Not deployed or session not restarted. Run `./install.sh` then restart. |
| `ModuleNotFoundError: requests` | Install deps (see Dependencies). |

---

## Context

Account: `steve@godding.net`, hosted on Fastmail. Mail forwarded from
`steve@godding.com.au` (Google Workspace) lands in the same inbox. The full
email estate and the "why Fastmail" history live in the personal knowledge vault
(`email.md`) and the `apple-family-email-setup` card.
