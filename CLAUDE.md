# AI Skills Repository

Personal repository for building, testing, and sharing Claude Code skills.

## Purpose

- Build custom Claude Code skills (SKILL.md + optional Python scripts)
- Evaluate and test skills created by colleagues (e.g., Leon's skills)
- Central knowledge base for skill patterns and lessons learned

## Installed Plugins (Marketplace)

M365 skills are now distributed via the Yambay marketplace (`yambay-tech/ai-assistants` on GitHub) and installed as plugins. Auto-update is enabled.

| Plugin | Version | Source | Description | Status |
|--------|---------|--------|-------------|--------|
| yambay@yambay-tech | v0.10.0 | Marketplace | Jira Cloud, defect-fixer, GTF compliance, SonarCloud, org context | Active |
| m365-core@yambay-tech | v3.0.3 | Marketplace | Email search/compose/reply + SharePoint/OneDrive file ops | Installed 2026-04-01 |
| m365-docs@yambay-tech | v2.3.0 | Marketplace | Markdown to Word conversion with styled templates | Installed 2026-04-01 |

Previous manual installs (`~/.claude/skills/email/`, `files/`, `md-to-word/`) were removed on 2026-04-01 to avoid duplicates.

## Shared M365 Configuration

All M365-connected skills share auth config at `~/.claude/m365/`:
- `.env` — TENANT_ID and GRAPH_CLIENT_ID (admin app: `772cbb4e...`)
- `.token_cache_skills.json` — Cached OAuth tokens (auto-created on first auth)

**Admin detection completed:** Steve is a Global Admin, so the setup switched from the shared skills app (`2f119494...`) to the admin app (`772cbb4e...`). This isolates admin-level scope grants from the shared app used by other staff.

**Graph API config** has been added to the global `~/.claude/CLAUDE.md` so Claude always uses the correct app for ad hoc M365 work.

## Skill Distribution

Leon's skills are now distributed via the **Yambay marketplace** (`yambay-tech/ai-assistants` GitHub repo). This replaces the previous SharePoint zip process.

### Installing marketplace plugins

```bash
claude plugin marketplace add yambay-tech/ai-assistants   # Add marketplace (one-time)
claude plugin install <plugin>@yambay-tech --scope user    # Install a plugin
```

Auto-update is enabled in `~/.claude/plugins/known_marketplaces.json`.

### Legacy: SharePoint zip process (deprecated)
The old zip-based distribution from `ClaudeCodeSetup` SharePoint site is no longer needed. Skills are managed as plugins with automatic updates.

## Dependencies

- Python 3 with: `python-docx`, `pyyaml`, `lxml`, `msal`, `requests`, `python-dotenv`, `markdown`
- pandoc (via Homebrew) — required by md-to-word skill
- Microsoft 365 account (Yambay) — required by files and email skills
- Install with `--break-system-packages` flag on macOS (PEP 668)

## Skills Management

Full documentation on how skills are organised, synced, and published is in the Obsidian work knowledge vault:
**`AI/Skills Management.md`** in `/Users/steve/Source/work/yambay-steveg/work-knowledge/`

Read that document for publish/retrieve commands and the full inventory.

## Repo Structure

- `skills/` — Custom Claude Code skills authored in this repo
  - `_template/` — Copy this to start a new skill (SKILL.md + scripts/ + tests/)
  - `email-tidy/` — SaneBox folder triage skill
  - `session-search/` — Search and resume past Claude Code sessions
- `raycast/` — Raycast script commands that launch Claude Code skills
- `warp/` — Warp terminal workflows and rules
  - `workflows/` — YAML workflow definitions
  - `rules/` — Markdown context rules
- `bin/` — Launcher scripts (`aiw`, `aip`) for Claude Code sessions
- `profiles/` — Notes on third-party skills under evaluation
- `install.sh` — Copies a skill from this repo to `~/.claude/skills/`
- `CLAUDE.md` — This file (project context for AI assistants)

## Building Skills

A Claude Code skill is a folder containing at minimum a `SKILL.md` with YAML frontmatter:
- `name` — skill identifier
- `description` — when to trigger (include example phrases)
- `allowed-tools` — which Claude Code tools the skill can use

The SKILL.md body contains instructions Claude follows. If the skill needs code, put scripts in `scripts/` and have the SKILL.md instruct Claude to call them.

### Workflow

1. `cp -r skills/_template skills/my-skill`
2. Edit SKILL.md and add scripts
3. `pytest skills/my-skill/tests/`
4. `./install.sh my-skill` (copies to `~/.claude/skills/`)
5. Restart Claude Code session

## Known Limitations

- No destructive-action guardrails in Leon's skills (email creates drafts not sends, but files can overwrite)
- No dry-run or confirmation prompts in scripts
- All M365 scripts request ReadWrite scopes, not Read-only
- Token cache at `~/.claude/m365/.token_cache_skills.json` — delete to force re-auth if issues arise
- SharePoint zip downloads were manual (MCP rejects `application/zip`) — now replaced by marketplace plugins

## Conventions

- Skills under evaluation go in `profiles/` with notes on testing outcomes
- Use Australian English spelling (organisation, colour, etc.) to match Yambay conventions
- Skill files reference paths like `~/.claude/skills/<skill-name>/` — keep this convention
- Keep this CLAUDE.md updated as skills are added, tested, or modified
