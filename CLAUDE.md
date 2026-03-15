# AI Skills Repository

Personal repository for building, testing, and managing AI assistant skills (starting with Claude Code, expanding to other tools).

## Purpose

- Evaluate and test skills created by colleagues (e.g., Leon's skills)
- Develop new custom skills for personal and company use
- Document skill patterns, installation procedures, and lessons learned
- Central knowledge base to return to across sessions

## Installed Skills (Local)

Skills are installed to `~/.claude/skills/` and are NOT stored in this repo (they contain user-specific config and credentials).

| Skill | Version | Location | Description | Status |
|-------|---------|----------|-------------|--------|
| md-to-word | v1.9 | `~/.claude/skills/md-to-word/` | Markdown to styled Word docs via pandoc + templates | Installed, untested |
| files | v1.4 | `~/.claude/skills/files/` | SharePoint/OneDrive file search, upload, download via Graph API | Installed, auth + search tested |
| email | v1.5 | `~/.claude/skills/email/` | M365 email search, compose, reply via Graph API | Installed, auth + search tested |

## Shared M365 Configuration

All M365-connected skills share auth config at `~/.claude/m365/`:
- `.env` — TENANT_ID and GRAPH_CLIENT_ID (admin app: `772cbb4e...`)
- `.token_cache_skills.json` — Cached OAuth tokens (auto-created on first auth)

**Admin detection completed:** Steve is a Global Admin, so the setup switched from the shared skills app (`2f119494...`) to the admin app (`772cbb4e...`). This isolates admin-level scope grants from the shared app used by other staff.

**Graph API config** has been added to the global `~/.claude/CLAUDE.md` so Claude always uses the correct app for ad hoc M365 work.

## Skill Source Location

Leon's skills are distributed as zip files on SharePoint:
- Site: `ClaudeCodeSetup` (Team Group ID: `6eead2ba-23b1-49b8-9557-7b0a39527e7a`)
- Path: `Shared Documents/Skills for Claude/`
- Installation guide: `How-to-Install-Skills.pdf` (v1.2, 2026-03-09)
- MCP tools cannot download zip files — must be downloaded manually via browser

## Installation Procedure

Steps to install a new skill (based on Leon's guide + lessons learned):

1. **Download** the zip from SharePoint to `~/Downloads` (manual — MCP can't fetch zips)
2. **Unzip** to `~/Downloads/<skill-name>`
3. **Copy** to `~/.claude/skills/<skill-name>/`
4. **Install Python deps:** `pip3 install --break-system-packages <packages>` (macOS managed Python requires `--break-system-packages`)
5. **Set up M365 auth** (if needed): Ensure `~/.claude/m365/.env` exists with TENANT_ID and GRAPH_CLIENT_ID
6. **Copy config templates** (files skill): `template/config/*.example.json` → `config/*.json`, then customise
7. **Test auth:** `python3 ~/.claude/skills/<skill>/scripts/test_auth.py` (opens browser on first run)
8. **Run admin detection** (one-time, if M365 skills): See email skill SKILL.md section 4
9. **Restart Claude Code session** so skills are loaded

## Files Skill Configuration

Fully configured at `~/.claude/skills/files/config/`:
- `paths.json` — OneDrive Personal + OneDrive-Yambay paths set
- `teams.json` — All 84 Yambay teams populated with Group IDs (auto-fetched from Graph API)
- `sites.json` — 5 key sites populated (Claude Code Setup, excom, Platform, Finance, AI Initiative)

To add more sites, query Graph API: `GET /groups/{groupId}/sites/root` then `GET /sites/{siteId}/drives`.

## Dependencies

- Python 3 with: `python-docx`, `pyyaml`, `lxml`, `msal`, `requests`, `python-dotenv`, `markdown`
- pandoc (via Homebrew) — required by md-to-word skill
- Microsoft 365 account (Yambay) — required by files and email skills
- Install with `--break-system-packages` flag on macOS (PEP 668)

## Repo Structure

- `profiles/` — Notes on skills created by team members (source, versions, what they do)
- `CLAUDE.md` — This file (project context for AI assistants)

## Known Limitations

- No destructive-action guardrails in Leon's skills (email creates drafts not sends, but files can overwrite)
- No dry-run or confirmation prompts in scripts
- All M365 scripts request ReadWrite scopes, not Read-only
- Token cache at `~/.claude/m365/.token_cache_skills.json` — delete to force re-auth if issues arise
- SharePoint zip downloads must be manual (MCP tool rejects `application/zip` MIME type)

## Conventions

- Skills under evaluation go in `profiles/` with notes on testing outcomes
- Use Australian English spelling (organisation, colour, etc.) to match Yambay conventions
- Skill files reference paths like `~/.claude/skills/<skill-name>/` — keep this convention
- Keep this CLAUDE.md updated as skills are added, tested, or modified
