# cardctl — the session-card launcher

Implements R12 (launch) + session-id capture from the spec (`README.md`). Dependency-free
Python 3 (no PyYAML — a minimal frontmatter parser for the card schema). macOS for now.

**Install / source of truth:** `ai-skills/session-cards/cardctl` is the source; `~/bin/cardctl`
is the on-PATH copy. After editing, re-copy:
`cp ~/Source/work/yambay-steveg/ai-skills/session-cards/cardctl ~/bin/cardctl`.

## Commands

```bash
cardctl launch <card.md>          # open the card's folders + resume its session (pin → latest → new)
cardctl launch <card.md> --new    # start a FRESH session (ignore pin / latest)
cardctl launch <card.md> --pick   # choose from the card's recent sessions (terminal only)
cardctl launch <card.md> -d       # start in bypassPermissions mode (skip approvals)
cardctl link   <card.md>          # pin the newest session id under the card's folder (--force to overwrite)
cardctl new    <slug> --title …   # scaffold a card in the Domain vault's Cards/ folder
cardctl reconcile [--apply]       # archive folders of cards marked archived/done (R9; dry-run by default)
```

## `reconcile` (R9 — card status → disk)

Scans every card in both vault `Cards/` folders; for any with `status: archived` (or `done`)
whose `paths` include an `active/<x>` folder, it **moves that folder to `archive/YYYY-MM-<x>`** in
its task repo (`git mv` + an `Archive:` commit) and updates the card's path. Cross-repo: card in
the vault, folder in the task repo. **Dry-run by default** — add `--apply` to perform the moves.
Skips a folder still referenced by a *live* (non-archived) card (R14 Pattern B). Run it at session
start (or on demand) to let board status drive the filesystem.

## Bringing existing work into the system (import process)

Turn an in-flight piece of work (already has sessions, maybe across repos) into a card:

1. **Find the session(s)** with the `session-search` skill (don't reinvent it):
   ```bash
   python3 ~/.claude/skills/session-search/search-sessions.py "<distinctive term>" --deep --json
   ```
   Note each result's `session_id` and `project` (= the cwd the session ran in). The most
   reliable term is a path or filename only that work touches (e.g. `endurance-testing.adoc`).
2. **Scaffold the card** — first `--path` is the **primary** (where the sessions ran, so resume
   works); add the other folders the work spans:
   ```bash
   cardctl new prodev-32988-endurance-testing-whitepaper \
     --title "PRODEV-32988 endurance testing whitepaper" \
     --path <project-cwd> --path <worktree> --path <task-folder> \
     --session <session_id> --jira PRODEV-32988 --area area/v7 --program "Work Ops"
   ```
3. **Open** the card in Obsidian (Reading view) → **▶ Launch session**.

Notes: pin the *active* session with `--session`; reach other sessions under the primary folder
via `cardctl launch <card> --pick`. Sessions under a *non-primary* path are only reachable by
pinning (a known limitation).

## New activity from scratch

```bash
cardctl new <slug> --title "…" --make-folder \
  --path <repo>/active/<slug> [--path <source repo/worktree> …] --area area/x
```

`--make-folder` creates the **primary path** (the activity folder) + a stub README. **Session
rooting:** the first `--path` becomes the new session's **cwd** (the extension uses
`workspaceFolders[0]` as cwd, the rest as `--add-dir`). So make the activity folder the first
`--path` → sessions root there (not at the repo top), and stay discoverable per-activity. This is
the fix for the old `aiw`-roots-at-repo-top behaviour; launch via the card instead of bare `aiw`.

### `launch`

1. Parses the card's frontmatter (`paths`, `sessionId`).
2. **Picks the session (R14 precedence):** `--new` → fresh; else pinned `sessionId`; else the
   **newest session created under the card's primary context folder** (`--pick` lists them with
   timestamps + a first-message preview to choose); else fresh.
3. Writes a generated `.code-workspace` (`~/.cache/session-cards/<card>.code-workspace`) and opens
   it with `code <ws>`. When resuming, the session's **origin folder is prepended** so the
   extension's workspace-scoped lookup finds it (see `../poc/TEST.md`). With **`-d`** the workspace
   carries `claudeCode.allowDangerouslySkipPermissions:true` + `initialPermissionMode:bypassPermissions`
   (window-scoped only; regenerated each launch — never touches your real folders).
4. After `--delay`s (default 1.5):
   - **resume** → fires `vscode://anthropic.claude-code/open?session=<id>`.
   - **new** → fires `vscode://anthropic.claude-code/open` (fresh conversation); prints a reminder
     to `cardctl link` if you want to pin it.

### Buttons (Obsidian)

The card's button bar maps to these, via Meta Bind templates → Shell Commands:
**▶ Launch session** (`launch`) · **✦ New session** (`--new`) · **⚡ Launch (skip approvals)**
(`-d`) · **📌 Pin latest** (`link --force`). See the operating note for the wiring.

### `link`

Finds the newest `*.jsonl` under the card's origin folder (first existing `paths` entry, or
`--cwd`), and writes its id into the card's `sessionId:` frontmatter (targeted edit — the rest
of the file is preserved verbatim). `--force` overwrites an existing id.

## Card schema

Cards live in the Domain vault's `Cards/` folder (R10/R13); `cardctl` takes a card path as its
argument.

```yaml
---
# --- human (shown on the board) ---
type: project         # project | program (bug/idea/decision optional)
title: ...
status: in-progress
summary: One line — what this is
latest: One line — current state and/or next step
tags: [area/tools]    # facet tags only: area/*, kind/*, jira/*
program: "[[Work Ops]]"            # hierarchy via wikilinks (on a project card)
# --- plumbing (cardctl; hidden on the board) ---
sessionId: <uuid>     # optional pin; set by `link` or hand-filled
paths:                # context folders — activity folder FIRST (= session cwd), then source repos
  - /path/to/activity-folder
  - /path/to/source-repo
---
```

`cardctl new` flags: `--summary`, `--latest`, `--title`, `--path` (repeatable), `--session`,
`--jira`, `--area`, `--program`, `--status`, `--make-folder`.
Note: `cardctl` only reads `paths`/`sessionId`; the rest are for the board/graph/consoles.

## Status / tested

- ✅ `launch` — resume (pin / latest-for-folder) and start-new, multi-root, origin auto-prepended;
  `--pick` chooser; `-d` bypassPermissions. Driven from Obsidian via the 4-button bar.
- ✅ `link` — captures newest session id, preserves the rest of the card file (`--force` to repin).
- ✅ `new` — scaffolds a card (`--make-folder` creates the activity folder).
- ✅ `reconcile` — archives folders of archived/done cards (dry-run + controlled `--apply` test).

## Not yet built (next)
- **Migration:** lives in the task folder for now; move to `~/bin` + the ai-skills repo `bin/`
  alongside `aiw`/`aip` (see memory `reference_aiw_aip_launchers`).
- Optionally run `reconcile` automatically at session start (a hook).
- Optionally extend `--pick` to search all card paths (non-primary sessions only reachable by pin).
