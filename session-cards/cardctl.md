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
cardctl set <card.md> [--area … --program … --raised-at … --customer … --add-tag … --remove-tag … --add-path …]  # write metadata (the /card-model apply-on-confirm writer)
cardctl lint [card.md] [--json]   # check cards for model drift (/card-model linter); --json = findings array
cardctl list [--json]             # list all cards across the Cards/ folders; --json = the board's read interface
cardctl focus  <card.md>          # bring the card's VS Code window to the front (Hammerspoon focus-by-id; AppleScript fallback)
cardctl windows [--json]          # list open VS Code windows mapped to cards (via Hammerspoon); --json = board read interface
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

## `lint` — model-drift linter (`/card-model`)

The integrity check the no-schema markdown card store needs. Scans every card (or one, if you pass
a path) and emits **facts** — it never edits anything. The `/card-model` skill consumes
`cardctl lint --json` and applies judgement; the board / CI can call it too.

```bash
cardctl lint           # grouped human report (error → warn → heuristic) + a summary line
cardctl lint --json    # [{card, code, severity, detail, fix, auto_safe}, …]
cardctl lint <card.md> # just that card (basename-collision is still scanned vault-wide)
```

Checks: `NO-AREA` (no `area/*` tag), `EMPTY-PROGRAM` (no `program:` while same-area siblings have
one), `DANGLING-LINK` (`program:`/`raised-at:`/`customer:` resolves to no vault note), `BASENAME-COLLISION` (a
note basename used by ≥2 notes vault-wide — breaks `shortest` link resolution; scaffolding stems
README/CLAUDE/AGENTS/index are exempt), `LINK-IN-PROSE` (a `[[…]]` buried in `summary:`/`latest:`/
`title:` instead of a link-property), `BAD-STATUS` (status outside the controlled vocabulary),
`MISSING-PLANID` (a `plan`-type card with no `planId`), `STALE-PATH` (a `paths:` entry that no
longer exists on disk), and the `STANDING-LANGUAGE` **heuristic** (ongoing/standing/recurring in
title/summary — a *candidate* for a Program/Forum note, the skill + you make the call).

## `set` — metadata writer (the apply-on-confirm fixes)

The validated writer behind `/card-model`'s low-risk fixes. Scope is deliberately reversible
metadata — the `area/*` facet, extra facet tags, and the `program:`/`raised-at:` link-properties.
It refuses any file outside a configured `Cards/` folder and never touches `status` (that stays
with `set-status`) or renames notes (an Obsidian-API job). Adding a link-property *value* to a card
is a create/edit, so a filesystem write is correct here.

```bash
cardctl set <card.md> --area area/v7                 # replace the area/* facet
cardctl set <card.md> --program managing-ai-activities  # set/repoint program: "[[…]]" home link
cardctl set <card.md> --raised-at e-and-a            # set raised-at: "[[…]]" provenance link
cardctl set <card.md> --customer sce                 # set customer: "[[…]]" stakeholder link (Customers/<slug>)
cardctl set <card.md> --add-tag kind/geospatial      # add a facet tag (repeatable)
cardctl set <card.md> --remove-tag kind/old          # remove a facet tag (repeatable)
cardctl set <card.md> --add-path ~/Source/work/…     # append a folder to paths (idempotent; repeatable)
cardctl set <card.md> --remove-path ~/Source/work/…  # remove a folder from paths (repeatable)
```

Existing inline (`tags: [a, b]`) vs block (`tags:\n  - a`) form is preserved; edits are surgical
so the vault git diff stays minimal.

## `list` — the board's read interface

`cardctl list --json` prints a JSON array (one object per card across every `Cards/` folder) shaped to
the board's card model, so the board maps it directly. Per card: `filePath` (absolute), `fileName`
(basename, no `.md`), `title`, `status`, `summary`, `latest`, `tags` (array), `program` and `project`
(wikilink-unwrapped — `[[Work Ops|Ops]]` → `Work Ops`), `customer` (**array** of slugs — a card can
serve several; scalar-or-list in frontmatter), `sessionId`, `paths` (array), `area` (the first
`area/<slug>` tag's slug, e.g. `tools`), `source` (the vault domain key, `work`/`personal`), and
`lastActive` (ISO-8601, timezone-aware — the newest session-transcript mtime across the pinned
`sessionId`'s transcript **and** every transcript under the card's `paths`, or `null` if the card has
no sessions; the board sorts on it for "most recently worked" and a live/recent badge). Scalar
values are unquoted and `ensure_ascii=False` keeps em-dashes etc. literal. Without `--json` it prints a
brief human listing (`title — status`). This is the read keystone for the board's hierarchy view.

## `windows` — open VS Code windows mapped to cards (Hammerspoon)

`cardctl windows --json` enumerates the open VS Code windows via **Hammerspoon** (`hs -c '<lua>'` runs Lua
in the running Hammerspoon and prints the result) and maps each to its card. Each generated window's title
is `"<card title> — <rootName> (Workspace)"` (`build_workspace` stamps the `window.title`; VS Code appends
` (Workspace)` and a trailing ` — Modified` when dirty), and the `<rootName>` segment is the card **slug**
(== the activity-folder basename == the card filename stem). `slug_from_window_title` strips those suffixes
and takes the substring after the *last* ` — ` separator, then we look the slug up against `{stem: card}`
across every `Cards/` folder.

The JSON is an **object, not a bare array**, so the board can tell *no windows open* from *engine
unavailable*:

```json
{"available": true,
 "windows": [{"id": 19146, "title": "…",
              "slug": "session-card-board", "filePath": "/…/session-card-board.md"}, …]}
```

`slug`/`filePath` are `null` for an unmatched window (manually-opened folder, or a slug with no card). On
engine failure (Hammerspoon not installed/running, ipc message-port unreachable, bad output) it emits
`{"available": false, "error": "<reason>", "windows": []}` and **exits 0** — so the board reads the JSON
and degrades, rather than treating it as a hard error. Without `--json` it prints a brief human listing.
This powers the board's session-panel v2 (open vs recently-closed). **Depends on Hammerspoon** with the ipc
module loaded (`hs` on PATH).

## `focus` — window-targeting primitive

`cardctl focus <card.md>` brings the VS Code window for that card to the front. VS Code's resume URI has
no window-targeting param, so this is the deterministic complement to launch's best-effort `activate` nudge.
It prefers a **Hammerspoon focus-by-id**: enumerate the `Code` windows (as `windows` does), find the one
whose title maps to this card's slug (the card filename stem, stamped into `window.title` by
`build_workspace`), and focus it by id (`hs.window.get(<id>):focus()`). **If Hammerspoon is unavailable, or
no window matches, it falls back** to driving macOS System Events (via `osascript`): set the `Code` process
frontmost and `AXRaise` the window whose title contains the card title. The AppleScript path **needs macOS
Accessibility permission** for the launching app (System Settings → Privacy & Security → Accessibility); the
whole thing is best-effort — if both paths fail it prints a clear message and returns rather than crashing.
(Launch is intentionally left as-is — the standalone `focus` is the safe primitive; wiring it into launch
is deferred so launch can never be blocked on an un-granted permission.)

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
shared-folder skip), `ensure_primary_folder`, `deploy` (the merge helpers + surface application
against a temp vault, asserting foreign settings survive), `slug_from_window_title`,
`windows --json` (matched/unmatched/engine-unavailable), and `focus` (id-upgrade + AppleScript
fallback). All hermetic — temp dirs / fixtures, the `hs`/`osascript` subprocess always mocked (never
a real Hammerspoon call or window raise), no real vault or `~/.claude/projects` writes.

## Bringing existing work into the system (import process)

Turn an in-flight piece of work (already has sessions, maybe across repos) into a card:

1. **Find the session(s)** with the `session-search` skill (don't reinvent it):
   ```bash
   python3 ~/.claude/skills/session-search/search-sessions.py "<distinctive term>" --deep --json
   ```
   Note each result's `session_id` and `project` (= the cwd the session ran in). The most
   reliable term is a path or filename only that work touches (e.g. `endurance-testing.adoc`).
2. **Scaffold the card.** A new card always gets its own activity folder, auto-created at
   `<active-root>/<slug>` as `paths[0]` (where its fresh sessions root). The work already ran
   *elsewhere*, so pin the existing session with `--session` and add its folders with `--path`
   (each `--path` is an **additional existing** folder, appended after the activity folder and
   not created):
   ```bash
   cardctl new prodev-32988-endurance-testing-whitepaper \
     --title "PRODEV-32988 endurance testing whitepaper" \
     --path <project-cwd> --path <worktree> --path <task-folder> \
     --session <session_id> --jira PRODEV-32988 --area area/v7 --program "Work Ops"
   ```
   (Pure pointer card with no activity folder of its own? Add `--no-folder`.)
3. **Open** the card in Obsidian (Reading view) → **▶ Launch session**.

Notes: pin the *active* session with `--session`; reach other sessions under the primary folder
via `cardctl launch <card> --pick`. Sessions under a *non-primary* path are only reachable by
pinning (a known limitation).

## New activity from scratch

```bash
cardctl new <slug> --title "…" [--path <source repo/worktree> …] --area area/x
```

A plain `cardctl new` is enough: the card's **activity folder is auto-created** at
`<active-root(domain)>/<slug>` (+ a stub README) and becomes `paths[0]`, so the card is launchable
immediately — no empty-`paths`/unlaunchable card. The per-domain `active-root` is `work →
…/claude-code-steveg/active`, `personal → …/ai-tasks/active` (`ACTIVE_ROOTS`, mirroring
`CARDS_DIRS`). **Session rooting:** `paths[0]` becomes the new session's **cwd** (the extension
uses `workspaceFolders[0]` as cwd, the rest as `--add-dir`), so sessions root in the activity
folder, not at a repo top.

Any `--path` entries are **additional existing folders** (e.g. a monorepo to link), appended
*after* the activity folder; they are not created (a missing one warns). `--make-folder` is now a
no-op kept for back-compat. Use `--no-folder` to opt out of the auto activity folder entirely (a
pure pointer card over `--path` folders; with no `--path` its `paths` is empty and it won't launch
— the explicit opt-out).

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
  - /path/to/activity-folder    # auto-created by `new` at <active-root>/<slug>
  - /path/to/source-repo        # additional existing folder (--path); linked, not created
---
```

`cardctl new` flags: `--title`, `--summary`, `--latest`, `--path` (repeatable; *additional
existing* folders), `--session`, `--jira`, `--area`, `--program`, `--status`, `--domain`,
`--no-folder` (opt out of the auto activity folder), `--make-folder` (now a no-op — the activity
folder is auto-created from the slug by default).
Note: `cardctl` only reads `paths`/`sessionId`; the rest are for the board/graph/consoles.

## Status / tested

- ✅ `launch` — resume (pin / latest-for-folder) and start-new, multi-root, origin auto-prepended;
  `--pick` chooser; `-d` bypassPermissions. Driven from Obsidian via the 4-button bar.
- ✅ `link` — captures newest session id, preserves the rest of the card file (`--force` to repin).
- ✅ `new` — scaffolds a card; auto-creates the activity folder from the slug at `<active-root>/<slug>`
  as `paths[0]` (`--path` = additional existing folders, appended after; `--no-folder` to opt out).
- ✅ `set-status` — surgical `status:` rewrite; validates the lifecycle vocabulary and refuses any
  card outside a configured `Cards/` folder. The single writer of the field — the board delegates here.
- ✅ `reconcile` — archives folders of archived cards (dry-run + controlled `--apply` test).
- ✅ `deploy` — single-sources every surface to both vaults + `~/bin`; idempotent, merge-safe;
  covered by the pytest suite and run end-to-end (`deploy all --apply` → clean re-run).
- ✅ `list` — JSON read interface for the board (full card model, wikilink-unwrap, `area` derivation,
  `source` domain key, `lastActive` recency timestamp) + a brief human listing; tested for
  shape/fields/multi-vault.
- ✅ `focus` — raises a card's VS Code window. Prefers Hammerspoon focus-by-id (matches the window whose
  slug == the card's), falling back to `osascript`/System Events AXRaise-by-title; best-effort, reports
  cleanly if Hammerspoon is unavailable and Accessibility permission is missing. Tested with both mocked.
- ✅ `windows` — lists open VS Code windows (via Hammerspoon) mapped to cards; `--json` emits
  `{available, windows:[…]}` so the board distinguishes "no windows" from "engine unavailable" (exits 0
  either way). Powers the board's session-panel v2. Tested with the `hs` subprocess mocked.
- ✅ **pytest suite** (`tests/`) — 61 hermetic tests across all commands + the deploy merges.

## Not yet built (next)
- **Phase 2 — the custom Kanban board** (a bespoke VS Code extension that renders the cards and
  fires `cardctl`). See the spec's "Custom Kanban board — PHASE 2".
- Optionally run `reconcile` automatically at session start (a hook).
- Optionally extend `--pick` to search all card paths (non-primary sessions only reachable by pin).
