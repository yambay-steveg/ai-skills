# Fastmail integration
<!-- card: /Users/steve/Source/work/yambay-steveg/work-knowledge/Cards/fastmail-integration.md -->

**Started:** 2026-06-27 (AWST)

Activity folder — sessions root here; working state lives here.

## What this is

A Claude Code skill that connects to Steve's personal Fastmail account
(`steve@godding.net`) over the **JMAP API** to **search, read, list, and draft**
email. **Draft-only by design** — it never sends; Steve reviews and sends from
Fastmail himself.

## Layout

- `SKILL.md` — triggers, setup, usage (the skill definition)
- `lib/jmap.py` — JMAP client (session discovery, bearer auth, batched calls)
- `scripts/` — `test_auth`, `list_folders`, `search_email`, `read_email`, `create_draft`
- `tests/` — offline unit tests for filter building (`pytest tests/`)

## Setup (one-time)

1. Fastmail → Settings → Privacy & Security → Manage API tokens → New token
   (scope: **Mail read & write**).
2. Put it in `~/.claude/fastmail/.env` as `FASTMAIL_API_TOKEN=...`.
3. `python3 scripts/test_auth.py` to verify.
4. `./install.sh fastmail-integration` (from repo root) to install to `~/.claude/skills/`.
