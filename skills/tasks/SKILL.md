---
name: tasks
description: >
  Manage Steve's Claude Code working folders (work + personal) — list active
  tasks, resume work, create new task folders, archive completed tasks, and
  clean scratch. Use when user says "what am I working on", "new task",
  "archive task", "clean scratch", "show tasks", "resume", "workspace", "ws",
  "tasks", or at session start when landed in a working folder.
allowed-tools: Bash, Read, Write, Glob, Grep, Edit, AskUserQuestion
---

# Tasks Skill

Manage the task folder lifecycle across Steve's two working folders.

## Scopes

Steve has two parallel working folders, each with `active/`, `archive/`, and `scratch/`:

| Scope    | Path                                                          | Git remote |
|----------|---------------------------------------------------------------|------------|
| work     | `/Users/steve/Source/work/yambay-steveg/claude-code-steveg/`  | `github.com-work:yambay-steveg/claude-code-steveg` |
| personal | `/Users/steve/Source/personal/ai-tasks/`                      | `github.com-personal:steve-godding/ai-tasks` |

Both are git repos. Archive moves get committed in their respective repo using the matching SSH host alias (already configured in each repo's remote — do not change remotes).

## Scope detection

Determine scope from the current working directory:

- cwd is `~/Source/work/yambay-steveg/claude-code-steveg/` or any subfolder → **work**
- cwd is `~/Source/personal/ai-tasks/` or any subfolder → **personal**
- Anywhere else → **ask** which scope the user wants

The user may override at any time ("show personal tasks", "new work task"). Honour explicit scope words over the cwd inference.

Always state the resolved scope in the first response so the user can correct it (e.g. "Work tasks:" or "Personal tasks:").

## Naming conventions

- Lowercase with hyphens: `quarterly-report-draft`
- Jira-linked work tasks: `PRODEV-1234-short-description` (work scope only — personal scope has no Jira)

## Commands

### Show active tasks

List the folders in `<scope>/active/`, with a one-line summary of each (check for `README.md`, `CLAUDE.md`, or infer from contents). Present as a numbered list so the user can pick one to resume.

### Resume a task

When the user picks a task (by number or name), `cd` into that folder and read any context files (README.md, notes, etc.) to get up to speed. Briefly summarise where things were left off.

### New task

Ask the user how they want to initiate the task. Available sources depend on scope:

| Source       | Scopes       | Flow |
|--------------|--------------|------|
| **Jira**     | work only    | Ask for the ticket key. Use Jira MCP tools or `/jira-cloud` skill to fetch summary, description, status. Name the folder `PRODEV-1234-short-description`. |
| **Email**    | work, personal | Ask for a search term (sender, subject, keyword). Use `m365-core:email`. Let user pick from results. Pull subject, sender, date, key content. (Note: M365 is Steve's work mailbox — for personal scope only use this if the task genuinely came from a work email that's gone personal, otherwise prefer Manual.) |
| **Manual**   | work, personal | Ask for a short description. |

Then:
- Create the folder under `<scope>/active/` using naming conventions
- Create a `README.md` inside with:
  - Task description
  - Date started (AWST)
  - Source context (Jira link, email subject/sender, or manual description)
- Confirm the folder is ready

### Archive a task

When the user says "archive [task]":
1. Move the folder from `<scope>/active/` to `<scope>/archive/` with a `YYYY-MM-` date prefix (AWST date). Use `git mv` so the rename is staged automatically and only the moved paths end up in the index.
2. Commit with message: `Archive: [task-name]`

The commit happens in the scope's git repo. SSH host aliases are already wired in each remote — no special handling needed.

**Do not** use `git add -A` or `git add .` to stage the archive — that risks sweeping in unrelated untracked or modified files that happen to be lying around. Stage only the source and destination paths of the rename.

If no task is specified, list active tasks and ask which to archive.

### Clean scratch

When the user says "clean scratch":
1. List everything in `<scope>/scratch/`
2. Ask for confirmation before deleting
3. Delete confirmed items (keep `.gitkeep` if present)

### Session start

When invoked at the start of a session (user just ran `aiw` or `aip`), present a menu like:

```
Scope: work    (~/Source/work/yambay-steveg/claude-code-steveg)

What would you like to do?

Active tasks:
  1. ag-planning
  2. certification-planning
  3. claude-skills
  4. sdom

  [number] Resume a task
  [n]      New task (manual)
  [j]      New task from Jira ticket    (work only)
  [e]      New task from email
  [a]      Archive a task
  [s]      Clean scratch
  [p]      Switch to personal tasks     (or [w] for work)
```

Wait for the user's choice before proceeding.

## Companion skills

This skill orchestrates folder lifecycle but delegates data retrieval to existing skills:

| Skill | Used for |
|-------|----------|
| `yambay:jira-cloud` | Jira queries with Yambay domain terms (PRODEV, MWFM, V6/V7, etc.) |
| `m365-core:email`   | Email search and retrieval via Microsoft Graph |
| `m365-core:files`   | OneDrive/SharePoint file access |
| Jira MCP tools      | Direct Jira issue lookups (preferred for simple `get issue` calls) |

Always use these existing skills rather than reimplementing their functionality.

## Notes

- Use Australian English spelling
- Both working folders are git repos — commit archiving moves in the correct repo
- Don't over-engineer folder contents; a README.md is enough scaffolding
- Times and dates are AWST (UTC+8)
