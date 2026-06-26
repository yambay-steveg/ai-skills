# PoC: multi-root workspace + resume-a-specific-session by URI

**Goal:** prove the make-or-break primitive — open several folders as one VSCode window, then
resume a *specific* Claude session by id, and have it actually resume (not silently start fresh)
even though the workspace is multi-root.

**Why it matters:** the whole launcher (R12) depends on this. If the `?session=` URI can't find
a session created under one of a multi-root workspace's folders, the design needs a different
resume mechanism (CLI `claude --resume` in an integrated terminal, or single-folder workspaces).

## Test fixture

- **Workspace:** `multiroot-resume-test.code-workspace` — two folders:
  1. `claude-code-steveg` (the repo the target session was created in) — listed **first**
  2. `yambay-tech/docutils-DocBookToWord` (a second, unrelated source repo)
- **Target session:** `81cd5424-8257-4374-b4e9-2b5986a0b8b2`
  - Created with cwd = `claude-code-steveg`
  - Recognisable opener: *"can you describe how I setup the cards and their uses"*

## Steps (run these — they touch the live VSCode UI, so you drive)

1. Close any current VSCode window for these repos (clean slate), then open the workspace:
   ```bash
   code "/Users/steve/Source/work/yambay-steveg/claude-code-steveg/active/session-card-system/poc/multiroot-resume-test.code-workspace"
   ```
   ✅ Expect: one VSCode window, Explorer shows **both** folders as roots. If prompted, **Trust** the workspace.

2. Fire the resume URI:
   ```bash
   open "vscode://anthropic.claude-code/open?session=81cd5424-8257-4374-b4e9-2b5986a0b8b2"
   ```
   ✅ PASS: the Claude panel opens showing the **prior conversation** (the "describe how I setup
   the cards" chat with its history).
   ❌ FAIL: a blank/fresh Claude conversation appears (means the session wasn't found in the
   multi-root context).

## Result — PASS (2026-06-24)

- [x] Step 1 — both folders open in one window: **YES** (both `task-repo` and `source-repo`
  showed as roots in the multi-root workspace).
- [x] Step 2 — session resumed with history: **PASS** — the URI resumed session `81cd5424`
  by id, with full prior history, inside the multi-root workspace. Resumed in a new editor tab
  ("Set up cards and their u…"), not the sidebar Sessions panel.
- **Notes / findings:**
  - The URI handler shows a **one-time security prompt** per extension: *"Allow 'Claude Code for
    VS Code' extension to open this URI?"* with a **"Do not ask me again for this extension"**
    checkbox. Tick it once → the launcher fires silently thereafter. (Important for automation.)
  - The extension's **Sessions** sidebar correctly lists recent sessions for the workspace
    (target appeared as "Set up cards and their uses"), confirming the workspace-scoped lookup.
  - Multi-root did **not** break the session lookup even though the session was created with a
    single cwd — the origin folder being present in the workspace was sufficient.

**Conclusion:** the launcher (R12) can rely on `code <ws>` + `vscode://anthropic.claude-code/open?session=<id>`.
Fallback ladder below is unused. Remaining build detail: ensure the card's origin folder is the
workspace root / present in `folders` so the resume lookup succeeds.

## Result 2 — new-session flow + cwd convention — PASS (2026-06-25)

Tested `cardctl launch <card>` with **no pinned session** (the new-session path: opens the
workspace + fires `vscode://anthropic.claude-code/open` for a fresh conversation). Card `paths` =
a single context folder (`…/active/session-card-system`).

- [x] A **fresh** Claude conversation opened in the workspace (no history). ✅
- [x] After a first message, the new session's transcript landed under
  **`~/.claude/projects/<encode(context-folder)>/`** — i.e. the new session's **cwd = the context
  folder**. The assistant itself confirmed "I'm in your session-card-system task folder". ✅
- [x] `cardctl link <card>` found that newest transcript and pinned its id into the card. ✅

**Conclusion:** the full loop works — *select card → start a fresh session in the right folder →
`link` to pin*. The **cwd convention holds**: when the context folder is the workspace folder, new
sessions are created there and are discoverable by folder. This de-risks R14 *resume-latest-for-
folder* (search `<encode(primary path)>` for the newest transcript).

## Result 3 — multi-root new-session cwd = folder[0] — PASS (2026-06-26)

The Result 2 caveat (single-folder only) is now closed, both ways:
- **Code:** the extension's `spawnClaude` maps `workspaceFolders → fsPath`, `shift()`s the first
  off, and passes `{cwd: folder[0], additionalDirectories: <rest>}`. So **folder[0] is the cwd**,
  the rest are `--add-dir`.
- **Empirical:** the endurance card (`paths[0]` = the activity folder, plus the worktree + docutils
  as extra folders) — clicking **✦ New session** started a fresh session that reported its cwd as
  `…/active/PRODEV-32988-endurance-testing-whitepaper` (the activity folder). ✅

**Convention locked:** list the **activity folder first** in the generated `.code-workspace` →
new sessions root there (not the repo top), and stay discoverable per-activity. This is the fix
for the old `aiw`-roots-at-repo-top behaviour.

## If FAIL — fallback ladder (try in order)

1. **Single-folder control:** open just the origin folder and retry the URI:
   ```bash
   code "/Users/steve/Source/work/yambay-steveg/claude-code-steveg"
   open "vscode://anthropic.claude-code/open?session=81cd5424-8257-4374-b4e9-2b5986a0b8b2"
   ```
   If this PASSES but the multi-root one FAILED → multi-root is the problem; launcher should make
   the **session-origin folder the workspace root** and/or use a single-folder window + `code --add`.
2. **CLI resume in integrated terminal** (bypass the URI):
   ```bash
   cd /Users/steve/Source/work/yambay-steveg/claude-code-steveg
   claude --resume 81cd5424-8257-4374-b4e9-2b5986a0b8b2
   ```
3. If even (2) fails from the repo root → session-id resume is cwd-bound more tightly than
   expected; revisit how cards store the origin folder.
