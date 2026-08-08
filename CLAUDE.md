# AI Skills Repository

Personal repository for building, testing, and sharing Claude Code skills and
command-line tooling — plus the **session-card system** (`cardctl`) that tracks
Steve's Claude Code work.

## Purpose

- Build custom Claude Code skills (SKILL.md + optional Python scripts)
- Develop and maintain standalone CLI tools deployed to `~/bin` (`cardctl`, `kb-lint`, launchers)
- Evaluate and test skills created by colleagues (e.g., Leon's skills)
- Central knowledge base for skill patterns and lessons learned

**This repo is the source of truth.** Anything on PATH (`~/bin/*`) or in a vault
(board, template, plugin config) is a *deploy target* — a copy. Edit here, then deploy
(see below). Never edit the deployed copy directly; the next deploy silently overwrites it.

## Repo Structure

- `skills/` — Custom Claude Code skills authored in this repo
  - `_template/` — Copy this to start a new skill (SKILL.md + scripts/ + tests/)
  - `card-model/` — Governance/linter skill for the session-card store (`/card-model`)
  - `tasks/` — Manage work/personal task folders — list, resume, create, archive (`/tasks`)
  - `email-tidy/` — SaneBox folder triage over Microsoft Graph
  - `session-search/` — Search and resume past Claude Code sessions
  - `fastmail-integration/` — Read/search/draft personal Fastmail over JMAP (draft-only)
- `session-cards/` — **The session-card system**: `cardctl` engine, spec, deploy surfaces, tests
- `bin/` — Standalone CLI tools + launchers (deploy target: `~/bin`)
- `raycast/` — Raycast script commands that launch Claude Code skills
- `warp/` — Warp terminal workflows (`workflows/`) and context rules (`rules/`)
- `profiles/` — Notes on third-party skills under evaluation (e.g. `leon.md`)
- `install.sh` — Copies a skill from this repo to `~/.claude/skills/`
- `requirements.txt` — Test/runtime Python deps (`pytest`, `python-dotenv`)
- `CLAUDE.md` — This file (project context for AI assistants)
- `AGENTS.md` — Codex-adapted variant of this file (**draft, unverified** — see note below)

## The Session-Card System (`session-cards/`)

The largest and most active part of this repo. A card-based work-tracking layer over
Claude Code sessions — the successor to the Nimbalyst trial. Read these to understand it:

- `session-cards/README.md` — the full requirements spec (R1–R15). The conceptual spine.
- `session-cards/cardctl.md` — the tool's command reference and operating guide.
- `session-cards/KNOWN-ISSUES.md` — current gaps.

### The model (in one breath)

**Layers: Area → Program → Card → Session.**

- **Card = a project** — the durable, trackable handle. Binds a *context folder* (`paths`) +
  its sessions + status + hierarchy. There is no separate "project" layer; a card *is* the project.
- **Session = a working slice of one card** — one Claude Code conversation (JSONL transcript),
  logged under the card's `## Sessions` heading. **Never its own card**; never spans cards.
- **Context (the folder) = memory** — accumulated state persists across sessions, so long work
  splits into short, resumable sessions without losing context. Durable state goes *into the folder*
  (e.g. `NOTES.md`), not left in a transcript.
- **Programs / Areas / Forums are vault *notes*, never cards.** Standing things get a stub note.
- **Hierarchy via wikilinks** (`program: "[[…]]"` in frontmatter); **facets via tags**
  (`area/*`, `kind/*`, `jira/*`).
- **Checkbox vs card test:** "will I open sessions to work on this, producing something — or is it a
  step I tick off within other work?" Most todos are `- [ ]` checkboxes; a card is its own stream of work.

Cards are **plain markdown files with frontmatter** in the Domain vault's `Cards/` folder — work
cards in `work-knowledge/Cards/`, personal cards in `personal-knowledge/Cards/`. Claude manages them
via the filesystem (no API/MCP/auth). Card `status` is the source of truth; the filesystem is
*reconciled from it* (one-directional, explicit, cross-repo).

### `cardctl` — the engine

`session-cards/cardctl` is a dependency-free Python 3 script (its own minimal frontmatter parser, no
PyYAML). **It is the single validated writer of card frontmatter** — the board and skills shell out to
it; nothing else hand-edits cards. Key commands (full reference in `cardctl.md`):

| Command | What it does |
| --- | --- |
| `cardctl new <slug> --title …` | Scaffold a card + auto-create its activity folder as `paths[0]` |
| `cardctl launch <card.md>` | Open the card's folders + resume its session (pin → latest → new) |
| `cardctl link <card.md> --current` | Pin the running session + log it under `## Sessions` |
| `cardctl unpin <card.md>` | Clear the `sessionId` pin (history kept) |
| `cardctl set <card.md> [--area/--program/--add-tag/--add-path …]` | Write reversible metadata |
| `cardctl set-status <card.md> <status>` | Set lifecycle status (the single writer of the field) |
| `cardctl lint [--json]` | Model-drift linter (emits facts, edits nothing) |
| `cardctl list [--json]` | The board's read interface (full card model as JSON) |
| `cardctl windows / focus` | Map/raise open VS Code windows to cards (macOS) |
| `cardctl reconcile [--apply]` | File folders of `archived` cards to `archive/` (dry-run default) |
| `cardctl which [folder]` | Reverse lookup: which card owns a folder (powers the SessionStart hook) |
| `cardctl deploy <work\|personal\|all> [--apply]` | Push canonical surfaces to a vault + `~/bin` |

Status vocabulary: `backlog` → `in-progress` → `on-hold` → `done` → `archived`. **A card is never
silently set to `done`/`archived`** — that's a deliberate, owner-confirmed action.

### Deploy model (source of truth → vaults + `~/bin`)

The card system is **maintained once in this repo, then deployed** to each vault and to `~/bin`.
Canonical surfaces live under `session-cards/deploy/` (board.base, Templates/card.md, the three
`.obsidian/*.json` plugin fragments). Deploy the engine, hook, and every surface with:

```bash
python3 session-cards/cardctl deploy all --apply
```

Dry-run by default; idempotent; the `.obsidian/*.json` files are **merged, never clobbered** (only
our entries by id/key), and vault notes are never touched. **Deploy refuses to run from a checkout
that isn't on `main`** (it ships the tree it reads to both live vaults) — run it from the worktree
holding `main`, or override deliberately with `--force`.

### Tests

```bash
cd session-cards && python3 -m pytest tests/ -q
```

Hermetic pytest suite (temp dirs/fixtures, all `hs`/`osascript`/window calls mocked — no real vault
or `~/.claude/projects` writes). Lint with `ruff check .` from `session-cards/` (config in `ruff.toml`;
`E702` intentionally ignored for the compact one-liner house style).

## Command-line tools (`bin/`)

Standalone tools, source-of-truth here, deployed by copying to `~/bin` (or, for the card tools, via
`cardctl deploy`). Never edit `~/bin/<tool>` directly.

| Tool | What it does |
| --- | --- |
| `bin/kb-lint` | Drift detector across both Obsidian vaults — cross-vault duplicates, unresolved links, orphans. The note-level counterpart to `cardctl lint`. |
| `bin/session-search` | Search Claude Code session history (also shipped as the `session-search` skill). |
| `bin/session-start-hook.sh` | SessionStart hook — resolves cwd to its card (via `cardctl which`) and injects status/latest so every session is card-aware. |
| `bin/local-only-branches` | Read-only audit of local git branches with no matching origin branch (age, PR state, unpushed commits). |
| `bin/aiw` / `bin/aip` | Launchers — open a work / personal AI task folder and start a session. |

## Skills in this repo

| Skill | Trigger | What it does |
| --- | --- | --- |
| `card-model` (`/card-model`) | "curate/audit/lint the cards", "is this a card or a checkbox" | Governance + linter over the card store. Thin reasoning layer; all mutations route through `cardctl` (never hand-edits frontmatter). |
| `tasks` (`/tasks`) | "what am I working on", "new task", "archive task", "resume" | Manage work/personal task-folder lifecycle (`active/`/`archive/`/`scratch/`); commits archive moves in the correct repo via SSH host aliases. |
| `email-tidy` | "tidy email", "triage sanebox" | Triage SaneBox folders via Microsoft Graph. Uses shared M365 config. |
| `session-search` | "find/search/resume session" | Search past Claude Code sessions by keyword/topic/recency (`history.jsonl` + transcripts). |
| `fastmail-integration` | "check my Fastmail", "draft a reply" | Read/search/draft personal Fastmail (`steve@godding.net`) over JMAP. **Draft-only — sending is intentionally unsupported.** |

## Installed Plugins (Marketplace)

M365 skills are distributed via the Yambay marketplace (`yambay-tech/ai-assistants` on GitHub) and
installed as plugins. Auto-update is enabled.

| Plugin | Version | Source | Description | Status |
|--------|---------|--------|-------------|--------|
| yambay@yambay-tech | v0.10.0 | Marketplace | Jira Cloud, defect-fixer, GTF compliance, SonarCloud, org context | Active |
| m365-core@yambay-tech | v3.0.3 | Marketplace | Email search/compose/reply + SharePoint/OneDrive file ops | Installed 2026-04-01 |
| m365-docs@yambay-tech | v2.3.0 | Marketplace | Markdown to Word conversion with styled templates | Installed 2026-04-01 |

Previous manual installs (`~/.claude/skills/email/`, `files/`, `md-to-word/`) were removed on
2026-04-01 to avoid duplicates.

### Installing marketplace plugins

```bash
claude plugin marketplace add yambay-tech/ai-assistants   # Add marketplace (one-time)
claude plugin install <plugin>@yambay-tech --scope user   # Install a plugin
```

The legacy SharePoint zip distribution (from the `ClaudeCodeSetup` site) is deprecated and no longer
needed — skills are managed as plugins with automatic updates.

## Shared M365 Configuration

All M365-connected skills share auth config at `~/.claude/m365/`:
- `.env` — TENANT_ID and GRAPH_CLIENT_ID (admin app: `772cbb4e...`)
- `.token_cache_skills.json` — Cached OAuth tokens (auto-created on first auth)

**Admin detection completed:** Steve is a Global Admin, so setup switched from the shared skills app
(`2f119494...`) to the admin app (`772cbb4e...`). This isolates admin-level scope grants from the
shared app used by other staff. Graph API config is in the global `~/.claude/CLAUDE.md` so Claude
always uses the correct app for ad hoc M365 work.

## Building Skills

A Claude Code skill is a folder containing at minimum a `SKILL.md` with YAML frontmatter:
- `name` — skill identifier
- `description` — when to trigger (include example phrases — this drives skill selection)
- `allowed-tools` — which Claude Code tools the skill can use

The body contains step-by-step instructions Claude follows. If the skill needs code, put scripts in
`scripts/` and have the SKILL.md instruct Claude to call them.

### Workflow

1. `cp -r skills/_template skills/my-skill`
2. Edit `SKILL.md` (name, description, trigger phrases, instructions) and add scripts
3. `pytest skills/my-skill/tests/`
4. `./install.sh my-skill` (copies to `~/.claude/skills/`)
5. Restart the Claude Code session to load the skill

## Dependencies

- Python 3 with: `python-docx`, `pyyaml`, `lxml`, `msal`, `requests`, `python-dotenv`, `markdown`
  - **Note:** `cardctl` itself is deliberately dependency-free (stdlib only).
- `pytest` for the test suites; `ruff` (or `uvx ruff`) for `session-cards/` linting
- pandoc (via Homebrew) — required by the md-to-word plugin
- Microsoft 365 account (Yambay) — required by files/email skills
- Install with `--break-system-packages` flag on macOS (PEP 668)

## Skills Management

Full documentation on how skills are organised, synced, and published is in the Obsidian work
knowledge vault: **`AI/skills-management.md`** in
`~/Source/work/yambay-steveg/work-knowledge/`. Read that document for publish/retrieve commands and
the full inventory.

## Known Limitations

- No destructive-action guardrails in Leon's skills (email creates drafts not sends, but files can overwrite)
- No dry-run or confirmation prompts in Leon's scripts
- All M365 scripts request ReadWrite scopes, not Read-only
- Token cache at `~/.claude/m365/.token_cache_skills.json` — delete to force re-auth if issues arise
- `cardctl` window/focus features (`windows`, `focus`) are macOS-only (CGWindowList/Hammerspoon/AppleScript)
- The custom Kanban board (spec Phase 2) is not built yet — status changes happen by editing `status:`
  (which is how Claude moves cards anyway); Obsidian Bases renders the board without a native drag view

## Conventions

- **Australian English spelling** (organise, colour, etc.) to match Yambay conventions
- **This repo is the source of truth**; `~/bin` and the vault surfaces are deploy targets — edit here, then deploy
- **Never hand-edit card frontmatter** — route every card mutation through `cardctl` (the single writer)
- **Never rename a vault note via shell/git** — renames must go through the Obsidian API (link-rewrite cascade)
- Skills under evaluation go in `profiles/` with notes on testing outcomes
- Skill files reference paths like `~/.claude/skills/<skill-name>/` — keep this convention
- Times and dates are AWST (UTC+8)
- Keep this CLAUDE.md updated as skills, tools, or the card system change

## AGENTS.md (Codex variant)

`AGENTS.md` is a Codex-adapted copy of this file (`~/.codex/…` paths, `codex …` commands). It is
marked **DRAFT — not yet verified** against the actual Codex CLI. Treat it as a starting point; when
you change this CLAUDE.md, consider whether AGENTS.md needs the mirror change, but don't rely on its
Codex-specific commands until they're confirmed.
