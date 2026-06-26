# Research: what to build the session-card system on

**Date:** 2026-06-24 (AWST)
**Question:** What can I leverage to (a) manage cards and (b) make selecting a card open the
right folders in VSCode *and* start/resume the matching Claude session?
**Context:** Obsidian = knowledge base. Moving Warp → **VSCode** as both editor and Claude
front-end (dropping JetBrains to save $100/yr). Cards link to one or more folders (typically a
task folder in the personal repo *plus* the separate source/content repo being worked on).

> Companion to `README.md` (the requirements spec). This is the "basis/tooling" research that
> feeds the still-open *Storage/architecture* and *UI surface* decisions in that spec.

---

## The one unavoidable conclusion

**No off-the-shelf board — Obsidian or VSCode — can fire an arbitrary external script from a
card tile out of the box.** Every option investigated hits this same wall. So the action
("open these folders + resume this session") must be a **thin launcher script I own**.

That's actually good news: it's exactly the pattern I already run with `aiw`/`aip`. The card
system just *supplies the parameters* (session id + folder list) to an evolved launcher.

## The two load-bearing mechanisms (both confirmed, both certain)

These are the parts that definitely work, and the whole design hangs off them:

1. **Opening arbitrary folders as one VSCode window** — generate a `.code-workspace` file.
   It's plain JSON: a top-level `folders` array of `{ "path": ... }` entries, **absolute paths
   allowed, no shared parent needed**. A script writes the JSON and runs `code that.code-workspace`
   — exactly what "Save Workspace As…" produces. (Or `code folderA folderB` opens both in one
   window without a file, since VSCode 1.16.)

2. **Resuming a specific Claude session in that window** — the VSCode extension registers a
   URI handler: `vscode://anthropic.claude-code/open?session=<session-id>` (optionally
   `&prompt=<url-encoded>`). It resumes that session in the currently-focused window. **Caveat:**
   the session must belong to the workspace that's open — if not found, it silently starts a
   fresh conversation.

   Fallback if the URI proves flaky: embed a `folderOpen` task in the `.code-workspace` that runs
   `claude --resume <id>` in the integrated terminal (subject to a one-time workspace-trust
   prompt), or just run the CLI directly.

## The end-to-end flow this enables

```
card { sessionId, paths: [taskFolder, sourceRepo, …] }
        │  (selected via a button / hotkey / URI in the card store)
        ▼
launcher script
  1. write /tmp/<slug>.code-workspace  ←  folders = paths (absolute)
  2. code /tmp/<slug>.code-workspace          (opens all folders, one window)
  3. open "vscode://anthropic.claude-code/open?session=<sessionId>"   (resume Claude)
```

For my worked example — a task folder in the personal repo that operates on a separate source
repo — the `.code-workspace` lists **both** folders; VSCode opens them as a multi-root window
and Claude resumes in the same window.

## Card-store options compared

| Option | Stores `{sessionId, paths}` | Board view | Trigger a script | Fit |
| --- | --- | --- | --- | --- |
| **Obsidian, note-per-card** | Yes — real frontmatter (`sessionId:`, `paths:`) | Kanban plugin *or* Bases (grouped) | **Shell Commands** plugin reads `{{yaml_value:…}}` and runs my script (ribbon button / hotkey / `obsidian://shell-commands` URI / Meta Bind button *in the note*) | **Best** — lives in my KB, fully local, richest metadata |
| **GitHub Projects v2 + official MCP** | Yes — native typed custom fields, free on personal acct | Native board | No (board UI won't run my script — still need the launcher) | Best if I want **Claude to manage cards programmatically** via `github-mcp-server` (`projects_write`) |
| **VSCode markdown-kanban** (LachyFS / AppSoftware, both active May 2026) | Yes — MD + YAML frontmatter, AI-writable | In-editor | No (cards can't run arbitrary VSCode commands; would need a custom extension) | Only if I want everything inside the editor and will build the trigger |

### Notes / caveats on each

- **Obsidian Kanban plugin** (mgmeyers): active again (v2.0.51, May 2026) but
  *governance-fragile* — "looking for maintainers" notice, low bus factor. Cards are list
  items, so on-*tile* metadata is inline-field text only and on-tile buttons are unreliable;
  the robust pattern is **one note per card** (link the note from the board) so the card has
  real frontmatter and a working button/URI.
- **Obsidian Bases** (native): note = card with typed properties, groups by property — but
  **no native Kanban/board view yet** (on the roadmap, "in development", no date). A community
  plugin (`obsidian-base-board`) fills the gap for now.
- **GitHub Projects v2**: cleanest *data + AI* story — but it's outside Obsidian, and selecting
  a card in its UI still can't launch anything locally; the trigger is my script either way.
- **VSCode boards**: the only one that ever ran per-card scripts (mkloubert) is archived; the
  living ones only fire their own built-in AI/worktree flows.

## Recommendation

**Obsidian note-per-card + Shell Commands + a launcher script**, with the board rendered by the
Kanban plugin (or a Bases board view).

Why it fits best:
- Cards live **with my knowledge base** — same vault, same markdown, same `area/*` tag
  vocabulary the spec already mandates (R4). A card note *is* a vault note.
- Fully local, free (no new subscription — the whole point of dropping JetBrains).
- Real structured frontmatter for `sessionId` + `paths`, which Shell Commands can pass to the
  launcher via `{{yaml_value:…}}`.
- The launcher is an evolution of `aiw`/`aip`, not a new moving part.

Keep **GitHub Projects v2** in mind as the alternative *if* the priority shifts to "Claude
should create/update cards itself" — its MCP + native custom fields are the cleanest for that,
at the cost of leaving the vault.

## Open items to verify before committing (cheap to test)

1. **Multi-root cwd precedence** — when a `.code-workspace` has several folders, which one
   becomes Claude's project root / where it looks for `CLAUDE.md` and finds the session? The
   session was created under one cwd (likely the personal repo root); the workspace must include
   that folder for the URI-handler resume to find the session. **Test:** open a 2-folder
   workspace, fire the resume URI, confirm it finds the session vs. starts fresh.
2. **URI-handler reliability + timing** — does `code <ws>` then immediately `open vscode://…`
   need a `sleep`, and does it target the right window? Decide URI vs. `folderOpen` task vs.
   plain CLI `claude --resume`.
3. **Kanban plugin longevity** — given the maintainer notice, confirm the board format
   round-trips as plain markdown (it does) so I'm never locked in if the plugin dies; Bases is
   the fallback board.
4. **Where session ids come from** — a card needs the id of an *existing* session, or to mint a
   new one on first launch and write it back to the note. Decide the capture step.
