# cardctl — the session-card launcher

Implements R12 (launch) + session-id capture from the spec (`README.md`). Dependency-free
Python 3 (no PyYAML — a minimal frontmatter parser for the card schema). macOS for now.

**Install / source of truth:** `ai-skills/session-cards/cardctl` is the source; `~/bin/cardctl`
is the on-PATH copy. After editing, **`cardctl deploy all --apply`** syncs the engine, the hook,
and every per-vault surface from this repo (see [`deploy`](#deploy--single-source-the-surfaces-r10)
below) — no hand-copying.

## Commands

```bash
cardctl launch <card.md>          # open the card's folders + resume its session (pin → latest → new)
cardctl launch <card.md> --new    # start a FRESH session (ignore pin / latest)
cardctl launch <card.md> --pick   # choose from the card's recent sessions (terminal only)
cardctl launch <card.md> -d       # start in bypassPermissions mode (skip approvals)
cardctl link   <card.md> --current   # pin the running session + log it under ## Sessions
cardctl link   <card.md> --session ID # pin a specific session id (e.g. one that ran elsewhere)
cardctl new    <slug> --title …   # scaffold a card in the Domain vault's Cards/ folder
cardctl set-status <card.md> <s>  # set lifecycle status (single writer of the field; surfaces delegate here)
cardctl reconcile [--apply]       # file folders of cards marked archived (R9; done is left in place)
cardctl which [folder] [--record] # which card owns a folder (reverse lookup; powers the SessionStart hook)
cardctl deploy <work|personal|all> [--apply]  # push the canonical surfaces to a vault + ~/bin (R10)
```

`cardctl which` resolves the card whose `paths` cover a folder (default: cwd) — used by the
SessionStart hook (`~/bin/session-start-hook.sh`) to make every session card-aware. `--record`
self-caches the link in a dedicated **`.card` dotfile** in the folder (validated on read; single
source of truth stays the cards' `paths`). The dotfile is a local cache — never written into the
folder's notes — and an older cardctl's legacy `<!-- card: … -->` README marker is stripped on next
record. (`.card` is gitignored in this repo.)

## `reconcile` (R9 — card status → disk)

Scans every card in both vault `Cards/` folders; for any with `status: archived` (or `done`)
whose `paths` include an `active/<x>` folder, it **moves that folder to `archive/YYYY-MM-<x>`** in
its task repo (`git mv` + an `Archive:` commit) and updates the card's path. Cross-repo: card in
the vault, folder in the task repo. **Dry-run by default** — add `--apply` to perform the moves.
Skips a folder still referenced by a *live* (non-archived) card (R14 Pattern B). Run it at session
start (or on demand) to let board status drive the filesystem.

## `deploy` — single-source the surfaces (R10)

Per the **one-management-home** principle (R10): the card system is maintained once, in this repo
(`ai-skills/session-cards/`), then *deployed* to each Domain vault and to `~/bin`. Without it, the
board/template/button/Templater/hook config drifts as it's hand-copied work↔personal.

```bash
cardctl deploy work          # dry-run: show what would change in the work vault + ~/bin
cardctl deploy all --apply   # write changes to BOTH vaults + ~/bin
```

**Canonical sources** live under `ai-skills/session-cards/deploy/`:

| Surface | Source | Dest (per vault, except ~/bin) | How |
| --- | --- | --- | --- |
| Bases board | `deploy/Cards/board.base` | `Cards/board.base` | copy |
| Card template | `deploy/Templates/card.md` | `Templates/card.md` | copy |
| Shell Commands | `deploy/fragments/shellcommands.commands.json` | `.obsidian/plugins/obsidian-shellcommands/data.json` | **merge** our 4 commands into `shell_commands` by `id` |
| Meta Bind buttons | `deploy/fragments/metabind.buttons.json` | `.obsidian/plugins/obsidian-meta-bind-plugin/data.json` | **merge** our 4 buttons into `buttonTemplates` by `id` |
| Templater | `deploy/fragments/templater.folder-template.json` | `.obsidian/plugins/templater-obsidian/data.json` | **merge** the `Cards`→`Templates/card.md` folder-template + enabling flags |
| Engine | `cardctl` | `~/bin/cardctl` | copy (+ `chmod 755`) — global, once |
| SessionStart hook | `../bin/session-start-hook.sh` | `~/bin/session-start-hook.sh` | copy (+ `chmod 755`) — global, once |

**Safety:** **dry-run by default** (`--apply` to write). Idempotent — only writes when content
actually changes (re-running a clean deploy reports *everything up to date*). The three
`.obsidian/*.json` files are **merged, never clobbered** — our commands/buttons/folder-template are
replaced-by-id/key while every other plugin setting (and any unrelated commands) is preserved. Only
the listed surfaces are touched — **never a vault's notes**. Editing a canonical source under
`deploy/` and running `deploy all --apply` is the supported way to change the surfaces.

**Editing surfaces:** change the file under `deploy/`, then `cardctl deploy all --apply`. (For the
Obsidian-plugin JSON, the easy authoring loop is: tweak it once in a vault via the Obsidian UI,
re-extract the fragment into `deploy/fragments/`, then deploy out to the other vault.)

## Tests

A pytest suite lives in `ai-skills/session-cards/tests/` — run from the `session-cards/` dir:

```bash
python3 -m pytest tests/ -q
```

It loads the extension-less `cardctl` as a module (`conftest.py`) and covers `parse_fm`,
`find_card_for`/`which` (+ the `.card` cache, stale-cache validation, and legacy-marker
migration), `resolve_session` pin
precedence, `link` (pin + `## Sessions` history + dedup), `reconcile` (dry-run, archived-only,
shared-folder skip), `ensure_primary_folder`, and `deploy` (the merge helpers + surface application
against a temp vault, asserting foreign settings survive). All hermetic — temp dirs / fixtures,
no real vault or `~/.claude/projects` writes.

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

1. Parses the card's frontmatter (`paths`, `sessionId`). **If the primary path (`paths[0]`, the
   activity folder) doesn't exist yet, it's created** (+ a stub README) — so a GUI-created card
   (new note in `Cards/`) launches cleanly: make a card → ▶ Launch → folder created + session
   starts, no `cardctl new` needed. (Only created when the parent dir exists, so a typo isn't
   fabricated deep.)
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

### `link` — pin a session + log history

Pins a session as the card's `sessionId` **and logs it under a `## Sessions` heading in the card
body** (the session history). Pick the session by:
- `--current` — the running session (the newest transcript across all projects).
- `--session <id>` — an exact id (needed for sessions that ran *outside* the card's folder, e.g.
  rooted at a repo top).
- *(default)* the newest transcript under the card's folder (`--cwd` to point elsewhere).

**Session history convention:** the card's **`## Sessions`** section is the readable log —
newest first, one bullet per session: `` - `<id>` — <date> — <what it did> ``. `cardctl link`
writes the `` `id` — date `` (and the displaced previous pin if not already logged); a session/AI
fills in the **"— what it did"** note. The frontmatter `sessionId` marks the *current* pin;
`## Sessions` is the durable history. Re-pinning is non-destructive — the old pin stays logged.
(`--force` is accepted but no longer needed.)

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
- ✅ `set-status` — surgical `status:` rewrite; validates the lifecycle vocabulary and refuses any
  card outside a configured `Cards/` folder. The single writer of the field — the board delegates here.
- ✅ `reconcile` — archives folders of archived cards (dry-run + controlled `--apply` test).
- ✅ `deploy` — single-sources every surface to both vaults + `~/bin`; idempotent, merge-safe;
  covered by the pytest suite and run end-to-end (`deploy all --apply` → clean re-run).
- ✅ **pytest suite** (`tests/`) — 31 hermetic tests across all commands + the deploy merges.

## Not yet built (next)
- **Phase 2 — the custom Kanban board** (a bespoke VS Code extension that renders the cards and
  fires `cardctl`). See the spec's "Custom Kanban board — PHASE 2".
- Optionally run `reconcile` automatically at session start (a hook).
- Optionally extend `--pick` to search all card paths (non-primary sessions only reachable by pin).
