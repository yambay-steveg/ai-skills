# Session Card System — requirements spec

**Started:** 2026-06-24 (AWST)\
**Scope:** Requirements only. *What* I need from a card-based work-tracking layer over my Claude Code sessions — tool-agnostic. No build, architecture, or UI decisions here yet.\
**Source:** Manual — distilled from the Nimbalyst design work after deciding to move off Nimbalyst.

---

## Why this exists

I trialled **Nimbalyst** as a card-based front over my Claude Code sessions and did a lot
of good thinking about what such a system needs. I've hit limitations running Nimbalyst and
am moving away from it, so I want to **keep the thinking and lose the tool**. This document
is that thinking, decoupled from Nimbalyst and reframed as a spec for a system I'd build (or
adopt) going forward — simpler than Nimbalyst, tailored to how I actually work.

Source material distilled here:
- `active/nimbalyst-workflow-integration/README.md` — the conceptual model + rationale
- `active/nimbalyst-local/plans/*.md` — worked examples of the model in use
- `active/claude-sessions-front-design/README.md` — the session-browsing angle (separate concern)

Everything below is a **requirement or a settled design principle**, not a Nimbalyst feature.

---

## The core idea (the insight worth keeping)

My old system has **one axis**: folders on disk (`active/` → `archive/`). A folder is both
*the work* and *the record of the work*.

The system I want splits that into **three things kept deliberately separate** (R14):

- **Context (the folder)** — *memory*. Accumulated state, notes, artifacts. Persists until
  archived. One per stream of work.
- **Sessions** — *working stints*. Each Claude Code chat is a session (JSONL transcript). The
  harness creates them; **many** sessions can work in one context.
- **Cards** — *durable, trackable handles* (`project`, `program`; optional `bug`/`idea`/`decision`)
  that bind a context + its sessions + status + hierarchy, independently of any one conversation.

**The principle that kills view-maintenance:** the cards *are* the work-record, created as a
byproduct of working. Every view is a disposable lens over them. I never maintain a chart —
I move a card and the board *is* the truth.

See **R14 (context/session/card model)** and **R15 (lifecycle & persistence)** below for the
full conceptual spine — they govern how R1–R13 are read.

---

## R1 — Vocabulary the system must model

Two independent dimensions, named so "task" stops being overloaded.

**Dimension 1 — Domain** (where it's stored & managed): **Work** or **Personal**. These map
to my two existing repos / git accounts / vaults / launchers. The system must keep them
strictly separate (no cross-Domain leakage).

**Dimension 2 — shape of the work:**

| Term | Time frame | What it is | How it's realised |
| --- | --- | --- | --- |
| **Activity** | hours–days | A self-contained job — respond to an email, fix an assigned defect, review someone's PR. Produces an outcome. **Usually a single session.** Often standalone; *may* link to a project/program, but not incessantly. | **a session** (a working stint), not its own card — see R14. Promote to a small `project` card only if independently trackable. |
| **Project** | days–weeks | A deliverable effort (a document, a system, a feature — **this work is a project**). Spawns multiple activities/sessions over its life. | a **`project` card** binding a context folder + its many sessions (R14). |
| **Program** | months+ | An ongoing theme that *contains* Projects | standing → a **stub note**; time-boxed → a **`program` card** (R5). |

"Task" is retired as a precise term — it survives only as the `/tasks` skill name.

> **✓ RESOLVED (2026-06-27, by dogfooding).** The reservation was: collapsing to two card tiers
> (`project` + `program`, Activity = a session — R14) leaves **lightweight actionable captures**
> with no home. Resolution: **they live as checkboxes, not cards.** Todos are `- [ ]` items in a
> card's body or its folder's `## Open actions`; a todo **graduates to its own `project` card**
> only when it becomes a *stream of work* (a deliverable, its own sessions, its own board status).
> So there are **three levels — checkbox / `project` card / `program`** — but only the middle and
> top are *cards*. No third card tier is needed. (See "Todos & ongoing work" below.)

**Design goal (a key driver):** today I keep one long-running session per stream of work,
because breaking it up risks losing accumulated context. This system should make me *comfortable
splitting long work into smaller sessions* — because the **context folder** carries the state
and any session can reload it (R14). Short, resumable sessions over one ever-growing one.

## R2 — Card types (two core + optional)

Nimbalyst's type set (`plan`/`task`/`bug`/`idea`/`decision`) was **fixed and imposed**. This is
my system, and because **an Activity is a session, not a card** (R14), the card types collapse to:

- **Core:** `project` (a **Project** — the workhorse card binding a context folder + its
  sessions) and `program` (the umbrella card for a **time-boxed Program**; standing programs
  need only a stub note — R5).
- **Optional — add only when one earns its place:** `bug`, `idea`, `decision`. Undecided whether
  I need them; don't build them in up front. `bug` may just be a `project`/folder with a `jira/`
  tag; `idea` and `decision` may be better as vault notes than board cards. Revisit on real use.

A *standalone Activity worth tracking* (the promoted case — R1) gets a small `project` card; it's
structurally a project (a folder + a session or two), just smaller, so it needs no separate type.
(`plan`→`project`; `task`/`activity` is **not** a card type — it's a session.) The lightweight-
capture worry this raised is **resolved** — todos are checkboxes, not cards (see *Todos & ongoing
work* below, and the resolved note in R1).

Cards carry at minimum: type, title, status, tags, free-text body, a context (`paths`), and links
to the session(s) under it. `project` cards additionally carry progress and a pointer to their
deliverable folder.

### Todos & ongoing work

One test decides where a todo lives: **"will I open sessions to work on this, producing something
— or is it a step I tick off within other work?"**

- **Checkbox** — a `- [ ]` in a card's body or the folder's `## Open actions`. A todo *within* a
  piece of work. Lightweight, zero ceremony — **most todos live here.**
- **`project` card** — when the todo is its *own stream of work*: a deliverable, its own sessions,
  its own board status. A checkbox **graduates** to a card when it earns it.
- **`program`** — an ongoing theme containing many of those.

A **follow-on deliverable** (e.g. "get the white paper reviewed by EXCOM" after the licensing
decision closes) becomes its **own `project` card with its own context** — *not* a reopen of the
finished card, and *not* sharing the finished card's folder (sharing couples lifecycles so the
folder can't archive — R13 Pattern B). Reference the archived folder if it needs the history.

**Rule carried over:** a `project` card is never silently set to done/completed — that's a
deliberate, owner-confirmed action.

## R3 — Hierarchy via wikilinks; tags for facets

The hierarchy is expressed with **Obsidian wikilinks**, *not* tags. (Nimbalyst forced
tags-only because it had no tracker→tracker link — that constraint is gone. In Obsidian, links
are first-class, cheap, rename-safe, and they power the **graph view**, which is exactly how I
want to *see* how programs, projects, and activities relate.)

**Split of concerns:**

- **Hierarchy → wikilinks (frontmatter).** An activity card links up to its project
  (`project: "[[Session card system]]"`); a project card links up to its program
  (`program: "[[Work Ops]]"`). The graph then shows **Program → Projects → Activities** as a
  real, navigable tree; click-through works; Obsidian auto-updates links on rename. Dataview /
  Bases can query "everything linking to `[[Project X]]`" for a console.
- **Facets → tags.** `area/*` (business area), `kind/*` (cross-cutting concern), `jira/*`
  (R4). These are *labels you filter by*, not a tree, so tags are the right tool — they stay.

**Board-tool caveat (couples to the still-open board-UI decision):** the Obsidian **Kanban
plugin** filters lanes by tag/text, not by link-query — so *if* I land on it I'll also keep a
complementary `project/<program>/<name>` tag for board filtering (some duplication). **Bases**
can query links directly, so links alone suffice there. Decide the complementary tag when the
board tool is chosen.

## R4 — Tag convention (slash + scoped)

The controlled vocabulary for **facet tags** (hierarchy itself is links — R3):

- **Work area** — `area/<slug>`, reusing the work-vault taxonomy (`area/ag`, `area/v7`,
  `area/v6`, `area/customer`, `area/docs`, `area/tools`, `area/hiring`, `area/admin`).
  Areas may be multi-tier (e.g. `area/customer/sce`).
- **Cross-cutting concern** — flat, opt-in `kind/<concern>` (e.g. `kind/geospatial`).
- **Jira (work only)** — `jira/<KEY>` when a card graduates to PRODEV/MWFM/FN scale.
- **Program / Project** — expressed as **wikilinks**, not tags (R3). *Conditional exception:*
  a complementary `program/<slug>` / `project/<program>/<name>` tag is added **only if** the
  chosen board tool needs tag-based filtering (i.e. the Kanban plugin, not Bases).

The tag vocabulary is shared with the Obsidian vaults — a card and a diary note both carry
the same `area/*` tag. The system reads/writes this vocabulary; it does not invent its own.

## R5 — Programs: standing vs time-boxed

A Program is a **note** (the link target / graph node for the cards under it — R3). They split
by lifecycle:

- **Standing** — runs indefinitely, never "done" (e.g. Eng Arch Mgmt). A **stub note** is
  enough — just a title to link to and appear in the graph; no umbrella `program` card, no status.
- **Time-boxed** — starts, runs, completes, rolls up (e.g. a trip, a 1–2 month initiative).
  The note is an umbrella `program` card carrying overall status/dates, archived when the Program
  wraps.

The system must not force an umbrella *`program` card* on standing Programs — a stub note suffices.
(This is the small cost of using links for hierarchy: even a standing program needs a note to
be a graph node. Worth it for the visual map.)

## R6 — Views are disposable lenses (Kanban-first, no Gantt)

**Status vocabulary** (controlled, so the board's `groupBy: status` doesn't fragment into
near-duplicate columns): `backlog` → `in-progress` → `on-hold` → `done` → `archived`.

- `backlog` / `in-progress` / `on-hold` = **active** (on the Board view; folder in `active/`).
  `on-hold` is a live pause (folder stays).
- **`done` = complete but not filed** — drops off the active Board (to a *Done* view), but the
  **folder stays in `active/`**. Reopen by setting it back to `in-progress` (nothing to un-move).
- **`archived` = filed** — the deliberate end state; `cardctl reconcile` moves the folder to
  `archive/` (R9). **Only `archived` is reconciled — `done` is left in place.**

The `done`↔`archived` split is intentional: clear something off the board the moment it's done,
without committing to filing it, since it may reopen. Archiving is a separate, explicit action.

- **Kanban board** with status columns is the primary view of "what's in play".
- Every other view is a disposable lens over the same cards:
  - **Facet lenses** = tag filters: `#area/*`, `#kind/*`, `#jira/`.
  - **Hierarchy lenses** (whole-Program / per-Project consoles) = link queries — "everything
    linking to `[[Program X]]` / `[[Project Y]]`" via Dataview/Bases (R3). *Or* tag filters
    `#program/*` / `#project/<program>/*` if the board tool needs the complementary tag (R4).
  - **The graph view** = the hierarchy seen as a navigable map (the payoff of links).
- A "just the actionable items" view = `project` cards in active statuses (hide `program`
  umbrellas and archived cards).
- **No Gantt.** I dislike them and they're maintenance overhead. Same cards, filtered views
  as lenses — nothing to keep in sync.

## R7 — Use cases the system must serve

| Need | Required capability |
| --- | --- |
| See "what's in play" | the Kanban board (status columns) |
| Views vary by activity | filtered board views (by tag / status) — same cards |
| Find an existing Project/Program/Activity | search over sessions + cards, plus board filter |
| Capture a spin-off mid-Project (reminder, change req, idea) without breaking stride | drop a lightweight card (a small `project`, or an `idea`/`decision` if enabled) into a backlog column, linked to the current Project. *(This is the case the R1 reservation worries about — see UNDER REVIEW.)* |
| Activity feedback-loop ("reopen before prod") | an `in-review` / `awaiting-deploy` column keeps it findable, off "in progress" |
| Recurring Program (weekly meeting → white papers → follow-ons) | a per-Program board view, ideally fed semi-automatically from inputs |
| Sub-Jira-scale work that today goes untracked | a **below-the-waterline** capture layer; promote a card to Jira when it graduates |
| "Where was I?" on resume | session view + the files a session touched |
| Low-maintenance status reporting | derive a "what moved" summary from card status/date changes (ties to the diary habit) |

## R8 — Relationship to sessions on disk

- Sessions already exist as Agent SDK **JSONL transcripts** keyed by cwd
  (`~/.claude/projects/<encoded-cwd>/`). The system layers cards over these — it does **not**
  own or replace them.
- Because sessions are keyed by folder, **a card's sessions are a derived view of its context
  folder** — discoverable on demand, not hand-maintained (R14). The card stores the *folder*;
  the sessions follow.
- A session "remembers" the files it touched (useful for the "where was I" case).

## R9 — Folder↔card sync: card status is the source of truth, disk is reconciled

- `/tasks` manages **folders on disk** (`active/` → `archive/` → `scratch/`). The card system
  manages **work items + sessions**.
- The card's **`status` is the source of truth**; the filesystem is reconciled *from* it. The
  sync is **one-directional and explicit**, not magic two-way auto-sync.
- **Default model — pull / reconcile-at-startup:** when I move a card (e.g. set it to
  *archived* in the board), nothing happens on disk immediately. **Next time Claude starts**, a
  reconcile step diffs card states against the filesystem and applies what's outstanding — e.g.
  a card now `archived` whose folder is still in `active/` triggers `git mv active/<task>
  archive/YYYY-MM-<task>` + an `Archive:` commit (reusing the existing `/tasks` mechanic). No
  daemon, fully local, slots into the `/tasks` session-start flow.
- **Cross-repo (because cards live in the vault — R10/R11):** card `status` lives in the
  **vault repo**; the folders it archives live in the **task repo**. So reconcile reads the card
  from the vault and `git mv`s the folder in the task repo — two repos, two commits. The card
  edit rides the vault's auto-backup; the folder move is an `Archive:` commit in the task repo.
- **Resume survives archiving.** A session's transcript is keyed by the cwd it ran in
  (`~/.claude/projects/<encode(path)>/`), so moving the folder would normally orphan it. Reconcile
  therefore **relocates the activity folder's transcripts** to `encode(archive path)` as part of
  the move — so the archived card is still resumable (history is never lost regardless; this keeps
  *resume-by-card* working too). (Legacy sessions rooted elsewhere, e.g. repo-top, aren't moved —
  recover those via the extension's global session history.)
- **Status: built + tested** — `cardctl reconcile` (dry-run default, `--apply` to perform); folder
  move + commit + card-path update + transcript relocation all verified in a controlled test.
- **Optional later — push / real-time:** a board action could fire Claude headless
  (`claude -p "archive <task>"`) or drop a pending-op into a queue file. More moving parts;
  parked unless the startup lag annoys me.
- The card system sits **on top of** the existing mechanics. `/tasks`, the two git accounts +
  SSH aliases, `aiw`/`aip`, both Obsidian vaults and their diary systems, and Jira/M365
  delegation all stay exactly as-is.

## R10 — Domain split: cards live in that Domain's Obsidian vault

Two Domains, kept separate: **Work** (vault `work-knowledge`) and **Personal** (vault
`personal-knowledge`). **Cards live in the Domain's vault**, in a dedicated **`Cards/`** folder —
work cards in the work vault, personal cards in the personal vault (never mixed; same rule as the
diary). The cards' `paths` point *out* at the task repos / source repos (absolute paths); the
task repos (`claude-code-steveg`, `ai-tasks`) still hold the work folders (`active/`/`archive/`)
that cards reference, but **the cards themselves are vault notes.**

Why the vault, not the task repo: it gives **one graph** — cards connect to diary entries and
permanent notes through shared `area/*` tags (R4) and the program/project wikilinks (R3) — and
the board renders in the vault I actually open in Obsidian. (See R15 on why transient cards in
the vault don't make it the "system of record": role ≠ location; the dedicated `Cards/` folder
cordons them.)

**Principle — one management home, two domains of data (2026-06-27).** The card *system itself*
(the `cardctl` tool, this spec, the operating docs, and the **deployable per-vault surfaces** —
`board.base`, `Templates/card.md`, the Shell Commands + Meta Bind button config) is **maintained
in a single home: the Work workspace (`yambay-steveg/ai-skills`)** — because that's where Steve
does most of his card-system work. It *operates on both domains' card data* (work cards in
`work-knowledge/Cards/`, personal cards in `personal-knowledge/Cards/`). So: **make system changes
once, in the work workspace, then deploy** the surfaces to each vault — don't fork per-vault
copies that drift. (The deploy step is a follow-up — see "still open".)

**Principle — `cardctl` is the engine, not the human interface (2026-06-27).** Steve should
rarely type `cardctl`. The day-to-day interfaces are: (a) the **GUI** — the Obsidian board +
button bar now, a custom VS Code/Kanban board later; and (b) a **conversational AI that knows
`cardctl`** ("new card for X", "archive this"), which it does via this doc + the SessionStart
card-awareness. The CLI is the substrate for the GUI, the AI, and automation — design for those
layers, not for hand-typing. Consequences: card *creation* should be frictionless without the CLI
(template auto-applied to `Cards/`, or "ask the AI"); the human-facing status default lives in the
**template** (`backlog`), and the AI sets status contextually — `cardctl`'s own CLI default is
secondary.

## R11 — Claude is the primary card-manager (so cards are plain markdown files)

I want **Claude to do most of the card management** — create, update, retag, change status,
reconcile — as a byproduct of working, with minimal manual board fiddling.

- This forces the storage choice: cards are **plain markdown files with frontmatter**, in the
  vault's `Cards/` folder (R10). Claude reads/writes them with the filesystem — no API, no MCP,
  no auth, no network.
- It rules *out* (as the primary store) any system whose cards have **no filesystem presence**
  (e.g. GitHub Projects / Linear): reconciliation (R9) would mean polling an API every startup
  instead of a local diff. Such a system stays a possible *secondary view*, not the source.
- A card file carries at least: type, title, `status`, tags, `paths` (the context folder(s) the
  card works on), body, and optionally a pinned `sessionId` and `outcomes` links (R13/R14/R15).
  Claude editing one of these *is* card management.

## R12 — Selecting a card launches the right workspace + a session

Selecting a card runs a thin **launcher** (an evolution of `aiw`/`aip`) that:

1. reads the card's `paths` and writes a `.code-workspace` listing those folders (absolute
   paths — typically the context folder *plus* the source/content repo it operates on);
2. opens it with `code <ws>` so VSCode shows all the folders as one window;
3. starts a session in that context. Because a card owns **many** sessions (R14), the launch
   offers: **resume the latest** session for the folder (the default — continue where I left
   off), **pick** from the folder's sessions, or **start fresh** (a new stint that still inherits
   the folder's state). Resume fires `vscode://anthropic.claude-code/open?session=<id>` (fallback:
   a `folderOpen` task running `claude --resume <id>`).

`sessionId` on a card is an **optional pin** (force a specific session), not the canonical
session list — that's derived from the folder (R8/R14). (Confirmed primitives:
`research-card-system-basis.md`.)

**Session rooting convention (the cwd fix).** A card's **`paths[0]` is the activity folder**, and
**that becomes the new session's cwd** — confirmed from the extension code: it uses
`workspaceFolders[0]` as `cwd` and the remaining folders as `additionalDirectories` (the
`--add-dir` set). So card-launched sessions root in the activity folder, *not* the repo top — which
is the whole point: sessions are then discoverable per-activity (resume-latest/`--pick` search
`paths[0]`). This is the fix for the old `aiw`-roots-at-repo-top problem; starting work via a card
replaces bare `aiw`. For a brand-new activity, `cardctl new --make-folder` creates `paths[0]` first
so it can be the workspace root.

Optionally start the session in **bypassPermissions** mode (`-d` / the ⚡ button) — written as
window-scoped settings in the generated `.code-workspace`, so it can even upgrade an *existing*
session on resume (permission mode is a property of the window, not the stored transcript).

**Status: built (on PATH), driven from Obsidian.** `bin/cardctl` (in `~/bin`): `launch`
resolves pin → latest-for-folder → new (`--new` forces fresh, `--pick` chooses, `-d` bypass);
`link` pins the newest session (`--force` repins). In the vault, a **4-button bar** on each card
(Meta Bind templates → Shell Commands) covers Launch / New / ⚡Dangerous / Pin. See `bin/README.md`
and the operating note. R14 launch model is **done**; the cwd convention held (the new-session
PoC — `poc/TEST.md` Result 2).

## R13 — Card files live in the vault's `Cards/` folder; they point at their context folder(s)

Cards live in a dedicated **`Cards/`** folder in the Domain's **Obsidian vault** (R10) — *not*
inside the context folders, and *not* in the task repo. Decided because a card is **decoupled
from its folder**: `program` umbrellas and `idea`/`decision` captures have no folder of their own
(R5/R7), and a context folder may be referenced by more than one card (R14, Pattern B). A card
*points at* its context via `paths` rather than living inside it — the **card is the trackable
handle, the folder is the memory**, kept separate (R14). Living in the vault gives the unified
graph + shared tags (R10).

**Layout:**
```
<domain vault>/              # work-knowledge (Work) | personal-knowledge (Personal)
├── Cards/
│   ├── board.base          # Obsidian Bases board: columns = group-by status (R6)
│   ├── <card>.md           # one note per card (frontmatter below)
│   ├── <Program>.md        # standing-program stub notes (link targets / graph nodes — R5)
│   └── …
├── Diary/ , Procedures/ …  # the rest of the knowledge base (one graph with the cards)

<domain task repo>/          # claude-code-steveg (Work) | ai-tasks (Personal)
├── active/<task>/           # context folder a card points at via `paths` (absolute)
├── archive/
└── scratch/
```

**Card frontmatter — two layers. A card is a *glanceable handle, not a document*: the human
fields show on the board, the plumbing drives `cardctl` and is hidden from the board.**

*Human (shown on the Kanban face):*
- `type` — `project` | `program` (bug/idea/decision optional — R2)
- `title`, `status`
- `summary` — one line, "what this is".
- `latest` — one line, current state and/or next step (the running where-it's-at note; the most
  Kanban-useful field — see what to do next without opening the card).
- `tags` — facets only: `area/*`, `kind/*`, `jira/*` (R4)
- `program:` / `project:` — hierarchy wikilinks (R3): `program: "[[…]]"` on a project card,
  `project: "[[…]]"` on a (rare) sub-card
- `outcomes` — *optional*, on completion: links to where the durable knowledge graduated (PR URL,
  `jira/` key, `[[Obsidian note]]`, email ref) (R15)

*Plumbing (for `cardctl`; not shown on the board):*
- `paths` — context folder(s): the activity folder first (R12), then external source repos (absolute)
- `sessionId` — *optional pin* of a specific session; the canonical session list is derived from
  the folder (R8/R14)

**Body — free-form and minimal, NOT a required structure.** Usually one line + a pointer to the
activity folder / `CONTEXT.md` where the deep state lives. Don't restate `paths` or session lists
(plumbing/derivable). Complex cards *may* add their own sections, but no body schema is mandated —
that would reintroduce the ceremony the system avoids.

**Interaction with R9 reconcile (cross-repo — card in vault, folder in task repo):**
- Only `paths` **inside a task repo's `active/`** are ever moved on archive. External/absolute
  source-repo paths are working references and are never touched.
- The **card note stays in the vault's `Cards/`** with `status: archived`; the board filters it
  off the active view. No `Cards/archive/`. Folder-archiving (task repo) = filesystem
  housekeeping; card status (vault) = work state. (Cost: reconcile updates the card's `paths`
  after the `git mv`, and commits in *both* repos.)
- **Shared folder (R14 Pattern B):** if more than one card lists the same `active/` folder,
  reconcile must not move it until *all* referencing cards are archived.

**Tooling note:** the board lives in the **Domain vault** I already open in Obsidian — no separate
"board vault". Card edits ride the vault's existing auto-backup; only the reconcile folder-moves
commit in the task repo.

## R14 — The context / session / card model (one card, many sessions)

Three entities, kept deliberately **separate** (none is forced to equal another):

| Entity | Role | Lifespan | Cardinality |
| --- | --- | --- | --- |
| **Context** (a folder) | **Memory** — accumulated state, notes, artifacts | persists until archived | one per stream of work |
| **Session** | **A working stint** — one Claude conversation, transcripted + resumable | ephemeral, replayable | **many** per context |
| **Card** | **The trackable handle** — binds a context (`paths`) + its sessions + status + hierarchy | lives with the work | 1 card → 1 context, many sessions |

- **State lives in the *folder*, not the session.** Sessions come and go; the folder carries
  knowledge between them. This is the mechanism that lets long work split into short, resumable
  sessions (the R1 design goal) without losing context.
- **Sessions are a *derived view* of the folder** (R8): Claude already keys transcripts by cwd,
  so a card never hand-maintains a session list — it stores the folder and the sessions follow.
- **An Activity = a session, not a card** (R1). The default shape is **one card (a `project`),
  many sessions** — the "activities" are just its stints. Promote a stint to its own card only
  when it's independently trackable.
- **Pattern A (default):** one card, many sessions, one shared folder.
  **Pattern B (when sub-work is independently trackable):** several cards listing the *same*
  folder in `paths` (N cards : 1 context) — see the R9/R13 archive caveat.
- **Discipline that makes multi-session work:** two sessions don't share live memory — they share
  the *folder*. So durable working state must be written **into the folder** (e.g. a `NOTES.md`),
  not left only inside a transcript.

> This two-tier card model (`project`/`program`, Activity = session) is the part Steve is
> re-examining — see the **UNDER REVIEW** flag in R1.

## R15 — Lifecycle & persistence: the card system is working memory, not the system of record

Knowledge has **two phases**, and this system owns only the first:

1. **In-flight (during the work):** working state lives in the **context folder** (R14), shared
   across sessions.
2. **At completion:** the keepers **graduate to their system of record** — Obsidian (knowledge),
   the repo/monorepo (code, docs), Jira (tracked work), email (comms). A deliberate outcome step.

Therefore, **once a card is complete, its folder + sessions are pure history** — searchable if I
ever want to retrace, but nothing load-bearing depends on them, because anything worth keeping
already lives elsewhere. Consequences:

- **The card system never competes with Obsidian.** It moves *work in motion*; the systems of
  record hold *settled knowledge*. Clean scope boundary.
- **Archiving is cheap and safe** (R9) — shelving history, not risking knowledge loss. Reconcile
  can be aggressive.
- **Completion implies graduation.** Optionally record where the output landed in the card's
  `outcomes` links (PR / `jira/` key / `[[Obsidian note]]` / email) — a "where did this end up?"
  trace that also enriches the graph (a done project visibly connects to its artifacts).
- This is the full answer to the long-session fear: **continuity in-flight (folder); permanence
  after (systems of record).** Nothing is trapped in a transcript.

---

## Explicitly out of scope / discarded (Nimbalyst-specific)

These are *not* requirements — they were Nimbalyst implementation details:

- The `nimbalyst.sqlite` DB, its tables, FTS, and rolling backups.
- The Nimbalyst MCP tools (`tracker_create`, `workspace_open`, etc.).
- The embedded Claude Agent SDK binary / `ClaudeCodeProvider` engine.
- The Nimbalyst id-bridge (`ai_sessions.id` ⇄ `provider_session_id`) and workspace re-rooting.
- The "NIM-n" card-numbering scheme.

A replacement system may *choose* its own storage and id scheme; nothing above mandates one.

---

## What's deliberately NOT decided here (next steps)

This is a requirements doc. Settled since the first draft (2026-06-24):

- **Storage** — *decided:* plain markdown + frontmatter in the Domain **vault's `Cards/` folder**
  (R10/R11) — for one graph + shared tags — so Claude manages cards via the filesystem.
- **Folder↔card sync** — *decided:* card `status` is the source of truth; disk reconciled at
  Claude startup, one-directional, **cross-repo** (card in vault, folder in task repo) (R9).
- **Card file layout** — *decided:* vault `Cards/` folder; cards point at context folders via
  `paths` (R13).
- **Conceptual model** — *decided (2026-06-25):* context/session/card kept separate; one card,
  many sessions; Activity = session (R14); knowledge graduates out, card system = working memory
  (R15). Hierarchy via links (R3); card types `project`/`program` (R2).
- **Board UI** — *decided (2026-06-25):* **Obsidian Bases**. Each card is a note; columns =
  group-by-`status`; hierarchy consoles = link queries (no complementary hierarchy tag needed);
  native core (no plugin-maintenance risk). Trade-off accepted: no native drag-board yet — status
  changes by editing the `status:` field, which is how Claude (the primary card-manager, R11)
  moves cards anyway. Rejected the Kanban plugin because it puts status in the board file's lanes
  (not the note frontmatter), treats cards as list-items (not notes), and filters by tag not link
  — all of which fight R9/R11/R13/R3 — plus it's maintenance-fragile.

Resolved by dogfooding:

- **Two-tier card model** (R2/R14) — the reservation (lightweight captures losing a card type) is
  **resolved**: todos are **checkboxes**, promoted to a `project` card only when they become a
  stream of work (R1 resolved note + *Todos & ongoing work*). No third card tier needed.

Still open, for a later pass:

- **Single-source the deployable surfaces (the principle's teeth)** — `board.base`,
  `Templates/card.md`, and the Shell Commands + Meta Bind button config currently exist as
  *copies* in each vault (the 27 Jun personal port copied them from the work vault). Per the
  "one management home" principle (R10), their canonical source should move to
  `ai-skills/session-cards/` with a small **`cardctl deploy <domain>`** (or shell script) that
  pushes them into a vault's `Cards/` + `.obsidian/plugins/`. Until then, board/template/button
  changes must be hand-copied work↔personal or they drift.
- **Drag-board UX (roadmap, not now)** — Bases has no native drag-board yet. Options when the
  itch arrives, in rough order of appeal:
  1. A **bespoke VS Code extension** that renders a Kanban over the card files **and** triggers
     `cardctl` (open folders + resume session) — this is the natural eventual UI because, unlike
     any off-the-shelf board, a board *I own inside VS Code* can fire the launcher (closes the
     "no off-the-shelf board runs a script" gap from `research-card-system-basis.md`). Doubles as
     the session-*browsing* front explored in `active/claude-sessions-front-design/`.
  2. A **standalone tiny Kanban** over the card markdown (simple to build, not Obsidian-coupled).
  3. The **native Bases Kanban view** when it ships, or a community `base-board` plugin.
- **Session-id capture** — confirm/choose how a new session's id is written back to its card
  (R12). *(The other half of this — whether `vscode://…?session=` resumes inside a multi-root
  workspace — is now **proven PASS**; see `poc/TEST.md`. One-time per-extension URI permission
  prompt has a "do not ask again" checkbox, so the launcher fires silently after first use.)*
- **Migration** — whether anything from the current Nimbalyst board is worth carrying over,
  or it's a clean start.
