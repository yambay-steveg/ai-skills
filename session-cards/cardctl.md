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
cardctl launch <card.md> --resume # force a tab for the pinned session (restore didn't)
cardctl link   <card.md> --current   # pin the running session + log it under ## Sessions
cardctl link   <card.md> --session ID # pin a specific session id (e.g. one that ran elsewhere)
cardctl unpin  <card.md>          # clear the sessionId pin (## Sessions history kept); inverse of link
cardctl note   <card.md> "what it did"  # write the note on the pinned session's ## Sessions entry
cardctl new    <slug> --title …   # scaffold a card in the Domain vault's Cards/ folder
cardctl set-status <card.md> <s>  # set lifecycle status (single writer of the field; surfaces delegate here)
cardctl set <card.md> [--area … --program … --raised-at … --customer … --add-tag … --remove-tag … --add-path …]  # write metadata (the /card-model apply-on-confirm writer)
cardctl lint [card.md] [--json]   # check cards for model drift (/card-model linter); --json = findings array
cardctl list [--json]             # list all cards across the Cards/ folders; --json = the board's read interface
cardctl focus  <card.md>          # bring the card's VS Code window to the front (Hammerspoon focus-by-id; cross-space workspace reopen; AppleScript fallback)
cardctl windows [--json]          # list open VS Code windows mapped to cards (zero-spawn native fast path; code --status + Hammerspoon fallback); --json = board read interface
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

Scans every card in both vault `Cards/` folders; for any with `status: archived`
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
README/CLAUDE/AGENTS/index are exempt), `CARD-STEM-COLLISION` (the same card filename stem in more
than one domain's `Cards/` folder — window↔card mapping for `windows`/`focus` keeps the first
match, so the rest silently mis-target), `LINK-IN-PROSE` (a `[[…]]` buried in `summary:`/`latest:`/
`title:` instead of a link-property), `BAD-STATUS` (status outside the controlled vocabulary),
`MISSING-PLANID` (a `plan`-type card with no `planId`), `STALE-PATH` (a `paths:` entry that no
longer exists on disk), and the `STANDING-LANGUAGE` **heuristic** (ongoing/standing/recurring in
title/summary — a *candidate* for a Program/Forum note, the skill + you make the call).

## `set` — metadata writer (the apply-on-confirm fixes)

The validated writer behind `/card-model`'s low-risk fixes. Scope is deliberately reversible
metadata — the `summary` line, the `area/*` facet, extra facet tags, and the
`program:`/`raised-at:` link-properties.
It refuses any file outside a configured `Cards/` folder and never touches `status` (that stays
with `set-status`) or renames notes (an Obsidian-API job). Adding a link-property *value* to a card
is a create/edit, so a filesystem write is correct here.

```bash
cardctl set <card.md> --summary "one-line what this is"  # the board's standing summary line
cardctl set <card.md> --colour violet                # window tint (token | #rrggbb | auto | none)
cardctl set <card.md> --area area/v7                 # replace the area/* facet (warns if unused elsewhere)
cardctl new <slug> --area v7 --strict                # refuse an area no existing card uses
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

**Facet membership is advisory (A4.4).** `new` and `set` validate an area's *shape* and then check whether any existing card already uses it — because the failure that actually happens is a well-formed typo (`area/tool` for `area/tools`), which passes every other check and silently mints a rival facet only `lint` notices later. Unknown areas print a note naming the near-misses and the areas in use, then proceed; `--strict` refuses instead. It stays advisory by default because the first card in a genuinely new area must not be blocked by a check whose only evidence is "nobody has used this yet". The vocabulary spans **both** vaults — areas are one taxonomy.

**Adding a folder to a card (a repo, a monorepo worktree) is `--add-path`, not a VS Code action.**
The `.code-workspace` is *generated* from the card's `paths` at
`~/.cache/session-cards/<card>.code-workspace` and rewritten on **every** launch, so a folder added
via VS Code's "Add Folder to Workspace" survives until the next launch and is then silently
discarded. The card is the source of truth; the workspace file is a derived artefact. Create the
folder first — `--add-path` only warns if it doesn't exist, leaving a folder that never appears.

`--summary` is quoted through the same YAML quoter as `cardctl new`, so prose containing a colon
or hash can't break Obsidian's frontmatter parse. Omitting the flag leaves an existing summary
untouched; passing `--summary ""` clears it deliberately.

### `latest` is a human line — the AI's next step goes in the task folder

Settled 5 Aug 2026, written down 8 Aug. **`latest` is Steve's glance line**: where the work stands,
in his words, for reading at a glance on the board. It is the card's most-read text — rendered on
the card face in both views, in the fly-out, and printed by the SessionStart hook.

**An AI's "what to do next" does not go there.** It goes in the card's activity folder, in
**`HANDOFF.md`** — the de facto convention already (five task folders use it; `NEXT.md` none). Deep
state, sequencing, blockers and open questions live there too, which is what the folder is *for*:

| Where | What | Audience |
| --- | --- | --- |
| `latest` (card) | where this stands, one line | Steve, glancing at the board |
| `HANDOFF.md` (activity folder) | next actions, blockers, sequencing | the next session |
| `## Sessions` (card) | what each session did, one line each | both, as durable history |

There is deliberately **no second card field** (`next:` or similar). A card is the wrong altitude
for a next-action queue, and the board face has no room to render one.

`--latest` therefore writes the *human* line. An AI updating it should write what Steve would write
("waiting on X", "shipped Y, Z still open") — not an instruction to itself. Getting this wrong is
what the convention exists to prevent: for months `latest` filled up with handoff prose, so the one
line meant for a human at a glance was written for a machine.

### `--colour` — which VS Code window is which

Each card carries a **window colour**, tinting its VS Code window's **status bar** so several
open cards are told apart at a glance. Status bar *only*: tinting the activity bar as well was
tried on four real windows (9 Aug) and read as noise rather than a hint — when every window
shouts, none stands out. Assigned at `cardctl new` from a 14-token palette,
**collision-aware** (never the same as a live card's), and stable for the life of the card. Cards
that predate tinting earn one on their first launch and keep it.

```bash
cardctl set <card.md> --colour violet     # a palette token
cardctl set <card.md> --colour "#4b2e83"  # or raw hex (foreground computed for contrast)
cardctl set <card.md> --colour auto       # reassign from the palette
cardctl set <card.md> --colour none       # opt out — no colorCustomizations written at all
```

Tokens rather than hex on the card so the palette can be retuned centrally without rewriting every
card, and so `colour: teal` stays readable in the file and in `list --json` (which lets the board
show the same colour later, if that's ever wanted).

**Not the title bar.** `titleBar.*` is ignored under macOS's native title bar, and
`window.titleBarStyle` is **APPLICATION-scoped** — a workspace file cannot change it (verified in
VS Code's own bundle: the setting registers with `scope: 1`). Tinting the title bar would need
`"window.titleBarStyle": "custom"` in User settings, globally, which changes how every VS Code
window looks. Left as an opt-in you can take later.

Archived cards release their colour: their windows aren't open, and a 14-token palette across ~69
cards would otherwise exhaust immediately.

## `list` — the board's read interface

`cardctl list --json` prints a JSON array (one object per card across every `Cards/` folder) shaped to
the board's card model, so the board maps it directly. Per card: `filePath` (absolute), `fileName`
(basename, no `.md`), `title`, `status`, `summary`, `latest`, `tags` (array), `program` and `project`
(wikilink-unwrapped — `[[Work Ops|Ops]]` → `Work Ops`), `customer` (**array** of slugs — a card can
serve several; scalar-or-list in frontmatter), `sessionId`, `paths` (array), `area` (the first
`area/<slug>` tag's slug, e.g. `tools`), `source` (the vault domain key, `work`/`personal`), and
`lastActive` (ISO-8601, timezone-aware — the newest session-transcript mtime across the pinned
`sessionId`'s transcript **and** every transcript under the card's `paths`, or `null` if the card has
no sessions; the board sorts on it for "most recently worked" and a live/recent badge), and
`sessions` (below). Scalar values are unquoted and `ensure_ascii=False` keeps em-dashes etc. literal.
Without `--json` it prints a brief human listing (`title — status`). This is the read keystone for the
board's hierarchy view.

### `sessions` — the card's `## Sessions` history, structured (ai-skills#41)

Each card object carries a `sessions` array: the card's `## Sessions` body list parsed into entries,
in card order (newest first, per the `link` convention). Per entry:

- `id` — the session uuid (the backticked lead of the line).
- `date` — the text between the first two `—` separators (e.g. `02 Jul 2026`; `:` accepted as a
  hand-written variant), `""` on a bare id-only line.
- `context` — the rest of the line (the "what this session did" note), `""` if absent.
- `resumable` — the transcript file still exists under `~/.claude/projects/…` (rarely false with a
  long `cleanupPeriodDays`; tolerance for hand-typed ids, not a UX signal).
- `projectDir` — the cwd recorded inside the transcript: the directory `claude --resume <id>` must
  run from (sessions run in worktrees, not just the card's activity folder). `null` when the
  transcript is missing or carries no cwd record.

Parsing is tolerant, never fatal: lines that don't match the entry shape (hand-written notes,
non-uuid backticks) are skipped, and a card without a `## Sessions` heading yields `[]`.

Design call: this rides `list --json` rather than a separate `cardctl sessions <card>` subcommand —
the board's `cardSource` already consumes `list --json` as its single read path (ADR 0001: the board
never parses card markdown), so the fly-out Session history (slice 6) needs no second process spawn
or per-card fetch.

## `windows` — open VS Code windows mapped to cards (native fast path + spawned fallback)

`cardctl windows --json` enumerates the open VS Code windows and maps each to its card. Engine order (#51):

1. **Native fast path (zero-spawn, ~90 ms, all Mission Control spaces).** Two reads, cross-checked:
   - **`storage.json`** (`~/Library/Application Support/Code/User/globalStorage/storage.json` →
     `windowsState.openedWindows`) — VS Code's own persisted state names *what* each window has open; a
     card's workspace is `<slug>.code-workspace`, so the slug falls straight out of the filename. Flushed
     within ~2 s of a window **opening**, but **not on close** — alone it would over-report.
   - **CGWindowList** (`CGWindowListCopyWindowInfo` via ctypes, no pyobjc, no subprocess, no Screen
     Recording permission for ids/bounds) — the live truth for *how many* real VS Code windows exist,
     across every space. Phantom window-server entries (native-tabs menubar strips, screen-width × ~30 pt)
     are filtered by height.

   When the two counts agree, the state list is current: rows are emitted directly, with OS window **ids**
   attached by matching the state's per-window geometry to live CG bounds (exact + unique — this maps ids
   even for windows on other spaces, which Hammerspoon never could). Titles are synthesised in the same
   `"<card title> — <slug> (Workspace)"` form VS Code renders. When the counts disagree (a window closed
   since the last flush), the fast path refuses and the spawned fallback re-syncs. Known edge: a close and
   an open inside the same ~2 s flush window can pass the count check with briefly wrong composition;
   self-heals on the next flush.
2. **Spawned fallback: `code --status` + Hammerspoon.** `code --status` reports every window (all spaces,
   titles only, seconds — run process-group-safe per #49); Hammerspoon overlays ids/focus where the
   Accessibility API can see them (current space only — #47). Either alone still yields a usable list
   (`code --status` down → Hammerspoon's current-space view; Hammerspoon down → all windows with null ids).

Each generated window's title is `"<card title> — <rootName> (Workspace)"` (`build_workspace` stamps the
`window.title`; VS Code appends ` (Workspace)` and a trailing ` — Modified` when dirty), and the
`<rootName>` segment is the card **slug** (== the activity-folder basename == the card filename stem).
On the fallback path `slug_from_window_title` strips those suffixes and takes the substring after the
*last* ` — ` separator; the slug is then looked up against `{stem: card}` across every `Cards/` folder.

The JSON is an **object, not a bare array**, so the board can tell *no windows open* from *engines
unavailable*:

```json
{"available": true,
 "windows": [{"id": 19146, "title": "…",
              "slug": "session-card-board", "filePath": "/…/session-card-board.md"}, …]}
```

`slug`/`filePath` are `null` for an unmatched window (manually-opened folder, or a slug with no card);
`id` is `null` when no engine could pin the OS window. Only when **every** engine fails does it emit
`{"available": false, "error": "<reason>", "windows": []}` — and it still **exits 0**, so the board reads
the JSON and degrades rather than treating it as a hard error. Without `--json` it prints a brief human
listing (`-` in the id column for a null id). This powers the board's session-panel v2 (open vs
recently-closed).

## `focus` — window-targeting primitive

**Window title layout (9 Aug 2026): `<slug> — <card title>`.** Window switchers (App Exposé,
Mission Control) truncate from the right, so with the human title first, several cards sharing a
name prefix were indistinguishable exactly where you most need to tell them apart — one of the
reasons window tinting was asked for. `${rootNameShort}` also drops VS Code's " (Workspace)"
decoration, reclaiming ~12 characters.

`slug_from_window_title` reads **both** layouts, told apart by that suffix (`${rootName}` carries
it, `${rootNameShort}` doesn't) — no card-store lookup needed. Windows opened before the change
keep their old titles until relaunched, so both are in play at once.

**If you change this format, the slug must stay recoverable**: `windows` and `focus` map a window
back to its card by parsing it, and the board's Focus button and open-or-focus decision depend on
that mapping.

`cardctl focus <card.md>` brings the VS Code window for that card to the front. VS Code's resume URI has
no window-targeting param, so this is the deterministic complement to launch's best-effort `activate` nudge.
It prefers a **Hammerspoon focus-by-id**: enumerate the `Code` windows (as `windows` does), find the one
whose title maps to this card's slug (the card filename stem, stamped into `window.title` by
`build_workspace`), and focus it by id (`hs.window.get(<id>):focus()`). When Hammerspoon has no match
(it can't see other Mission Control spaces — #47) but the window is confirmed open (native fast path,
falling back to `code --status` — same order as `windows`), it
upgrades to a **workspace reopen**: `code <cached .code-workspace>` raises the existing window and macOS
follows it to its space (guarded — `focus` never opens a *closed* workspace). Last resort: drive macOS
System Events (via `osascript`) — set the `Code` process frontmost and `AXRaise` the window whose title
contains the card title. The AppleScript path **needs macOS Accessibility permission** for the launching
app (System Settings → Privacy & Security → Accessibility); the whole thing is best-effort — if every path
fails it prints a clear message and returns rather than crashing.
(Launch is intentionally left as-is — the standalone `focus` is the safe primitive; wiring it into launch
is deferred so launch can never be blocked on an un-granted permission.)

## `deploy` — single-source the surfaces (R10)

Per the **one-management-home** principle (R10): the card system is maintained once, in this repo
(`ai-skills/session-cards/`), then *deployed* to each Domain vault and to `~/bin`. Without it, the
board/template/palette-command/Templater/hook config drifts as it's hand-copied work↔personal.

```bash
cardctl deploy work          # dry-run: show what would change in the work vault + ~/bin
cardctl deploy all --apply   # write changes to BOTH vaults + ~/bin
cardctl deploy all --force   # deploy from a non-main checkout (deliberate; warns loudly)
```

**Deploy refuses to run from a source checkout that isn't on `main`.** This matters more than it
looks: deploy ships whatever tree it reads to `~/bin` **and both live vaults**, and when cardctl is
invoked as the installed `~/bin` copy, its source is a *hardcoded fallback path*
(`~/Source/work/yambay-steveg/ai-skills/session-cards`) rather than your current directory. So the
source can silently be a feature branch you forgot was checked out there — which has happened twice:
the July slice-1a brief was written against a stale checkout, and on 6 Aug that clone was sitting on
`cardctl-customer-edge` with an unmerged commit while three merged PRs were being deployed. A
detached or undeterminable HEAD is refused too: if the source can't be named, it can't be called
releasable. `--force` overrides and says so on stderr.

Note the fallback path can't always hold `main` — if another worktree has `main` checked out, git
won't let that clone switch to it. Run deploy from the worktree that *does* hold `main`:
`python3 <main-worktree>/session-cards/cardctl deploy all --apply`.

**Canonical sources** live under `ai-skills/session-cards/deploy/`:

| Surface | Source | Dest (per vault, except ~/bin) | How |
| --- | --- | --- | --- |
| Bases board | `deploy/Cards/board.base` | `Cards/board.base` | copy |
| Card template | `deploy/Templates/card.md` | `Templates/card.md` | copy |
| Shell Commands | `deploy/fragments/shellcommands.commands.json` | `.obsidian/plugins/obsidian-shellcommands/data.json` | **merge** our 1 command into `shell_commands` by `id` |
| Templater | `deploy/fragments/templater.folder-template.json` | `.obsidian/plugins/templater-obsidian/data.json` | **merge** the `Cards`→`Templates/card.md` folder-template + enabling flags |
| Engine | `cardctl` | `~/bin/cardctl` | copy (+ `chmod 755`) — global, once |
| SessionStart hook | `../bin/session-start-hook.sh` | `~/bin/session-start-hook.sh` | copy (+ `chmod 755`) — global, once |

**Safety:** **dry-run by default** (`--apply` to write). Idempotent — only writes when content
actually changes (re-running a clean deploy reports *everything up to date*). The three
`.obsidian/*.json` files are **merged, never clobbered** — our command/folder-template entries are
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
3. **Launch it from the board** (open-or-focus).

Notes: pin the *active* session with `--session`; reach other sessions under the primary folder
via `cardctl launch <card> --pick`. `link` (both `--current` and its default search) covers **all**
the card's paths, so a session that ran in a linked repo or worktree is pinnable; `--pick` is still
primary-folder-only.

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
   extension's workspace-scoped lookup finds it (see `../poc/TEST.md`). The workspace always
   carries `claudeCode.allowDangerouslySkipPermissions:true` — bypass is **armed** (available in
   each tab's mode selector) but never forced; every session dials its own mode (window-scoped
   only; regenerated each launch — never touches your real folders).
4. **Usually stops there — VS Code restores the card window's Claude tabs itself.**

   Verified 8 Aug 2026: quit VS Code with one session open, reopen the workspace by hand, and the
   conversation comes back. `launch` used to fire the resume URI *anyway*, which opened a **second
   tab of the same session** — a duplicate on every single launch. (July's finding F5, "tabs
   accumulate", was this bug seen from the outside and treated as tidying.)

   So the session URI now fires **only when there is nothing to restore**:
   - **`--new`** → `vscode://anthropic.claude-code/open` (fresh conversation); prints a reminder
     to `cardctl link` if you want to pin it.
   - **`--resume`** → `…/open?session=<id>`, for when restore brought nothing back (you closed the
     tabs, or workspace state was cleared).
   - **first launch of this card's workspace** → same resume URI, since VS Code holds no state for
     it yet. Tracked by a `<card>.launched` marker beside the generated workspace in
     `~/.cache/session-cards/`, rather than by reading VS Code's own storage — that is
     undocumented, versioned, and would break silently on an update.

   **Window polling now runs only on those paths.** The URI has no window-targeting parameter, so
   it lands in whichever window has focus; `launch` therefore polls Hammerspoon (up to `--delay`s,
   default 3) until the card's window is open **and frontmost**, raising it by window id if
   needed, and exits without firing if it never gets there. A plain relaunch fires nothing, so it
   skips the poll entirely — which removes the wrong-window race from the common path instead of
   merely mitigating it. `--no-poll` keeps the old fixed-delay-then-fire behaviour; an unavailable
   Hammerspoon falls back to it automatically, with a note.

### Launching from Obsidian (R14: the board owns launching)

**The in-note button bar is retired.** Cards carried a Meta Bind button bar (▶ Launch session ·
✦ New session · 📌 Pin latest) wired through Shell Commands. It's gone: the board is the launch
surface, a card body is a *record* rather than a control panel, and the Shell Commands plugin's
settings UI is broken on current Obsidian (every tab throws; upstream's last release was Nov 2024),
so it was an unmaintained dependency in the middle of the primary workflow.

What remains in Obsidian is **one command-palette entry**, "Launch card" (`cardctl launch <file>`),
kept deliberately as a keyboard route into a card if the board is ever down. Everything else —
new session, pin, focus — happens on the board.

`cmd_new` therefore writes **no** button bar, and the deployed template has none: otherwise every
new card would re-seed the retired buttons one at a time.

### `link` — pin a session + log history

Pins a session as the card's `sessionId` **and logs it under a `## Sessions` heading in the card
body** (the session history). Pick the session by:
- `--current` — the running session (the newest transcript across all projects).
- `--session <id>` — an exact id (needed for sessions that ran *outside* the card's folder, e.g.
  rooted at a repo top).
- *(default)* the newest transcript under **any** of the card's paths (`--cwd` to narrow to one).
  A card's sessions often run in a linked repo rather than its activity folder, so searching only
  `paths[0]` failed with "no sessions found" while the session sat one path along.

**Session history convention:** the card's **`## Sessions`** section is the readable log —
newest first, one bullet per session: `` - `<id>` — <date> — <what it did> ``. `cardctl link`
writes the `` `id` — date `` (and the displaced previous pin if not already logged); **`cardctl
note` writes the "— what it did"**:

```bash
cardctl note <card.md> "swept the vaults and retired the buttons"   # the pinned session
cardctl note <card.md> "did the earlier half" --session <id>        # an older entry
cardctl note <card.md> ""                                           # clear it
```

It rewrites that one line and leaves every other byte alone — the history is hand-readable
markdown that also carries lines cardctl doesn't parse. With this, **nothing on a card needs a
hand-edit**: `## Sessions` was the last exception to the single-writer rule. The frontmatter `sessionId` marks the *current* pin;
`## Sessions` is the durable history. Re-pinning is non-destructive — the old pin stays logged.
(`--force` is accepted but no longer needed.)

### `unpin` — clear the pin, keep the history

`cardctl unpin <card.md>` removes the `sessionId` line and leaves `## Sessions` untouched, so the
next `launch` starts a **fresh** session in the card's own folder instead of resuming a stale or
wrongly-scoped one. This is the normal lifecycle action for standing/dormant cards (e.g. after an
origin session that ran at a repo root rather than the activity folder) — before it existed, the
only way to unpin was hand-editing frontmatter, which is exactly what cardctl's single-writer rule
forbids. Already-unpinned cards are a no-op, not an error. Same guards as `set-status`: the card
must exist and sit inside a configured `Cards/` folder.

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
sessionId: <uuid>     # optional pin; set by `link`, cleared by `unpin` (never hand-edited)
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
  `--pick` chooser. Driven from the board (and the one "Launch card" palette command).
- ✅ `link` — captures newest session id, preserves the rest of the card file (`--force` to repin).
- ✅ `new` — scaffolds a card; auto-creates the activity folder from the slug at `<active-root>/<slug>`
  as `paths[0]` (`--path` = additional existing folders, appended after; `--no-folder` to opt out).
- ✅ `set-status` — surgical `status:` rewrite; validates the lifecycle vocabulary and refuses any
  card outside a configured `Cards/` folder. The single writer of the field — the board delegates here.
- ✅ `reconcile` — archives folders of archived cards (dry-run + controlled `--apply` test).
- ✅ `deploy` — single-sources every surface to both vaults + `~/bin`; idempotent, merge-safe;
  covered by the pytest suite and run end-to-end (`deploy all --apply` → clean re-run).
- ✅ `list` — JSON read interface for the board (full card model, wikilink-unwrap, `area` derivation,
  `source` domain key, `lastActive` recency timestamp, `sessions` history with resume resolution) + a
  brief human listing; tested for shape/fields/multi-vault.
- ✅ `focus` — raises a card's VS Code window. Prefers Hammerspoon focus-by-id (matches the window whose
  slug == the card's); upgrades to a workspace reopen when the window is open on another Mission Control
  space (#47); falls back to `osascript`/System Events AXRaise-by-title; best-effort, reports cleanly if
  Hammerspoon is unavailable and Accessibility permission is missing. Tested with all engines mocked.
- ✅ `windows` — lists open VS Code windows mapped to cards. Native zero-spawn fast path (#51:
  storage.json windowsState × CGWindowList via ctypes, ~90 ms, all spaces, ids attached by geometry);
  falls back to `code --status` (all-spaces titles, #47) + Hammerspoon id overlay when persisted state
  disagrees with the live window count. `--json` emits `{available, windows:[…]}` so the board
  distinguishes "no windows" from "every engine unavailable" (exits 0 either way). Powers the board's
  session-panel v2. Tested with all engines mocked.
- ✅ **pytest suite** (`tests/`) — 61 hermetic tests across all commands + the deploy merges.

## Not yet built (next)
- **Phase 2 — the custom Kanban board** (a bespoke VS Code extension that renders the cards and
  fires `cardctl`). See the spec's "Custom Kanban board — PHASE 2".
- Optionally run `reconcile` automatically at session start (a hook).
- Optionally extend `--pick` to search all card paths (non-primary sessions only reachable by pin).
