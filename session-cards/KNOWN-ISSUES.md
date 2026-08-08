# cardctl — known issues

Running log of launcher/engine bugs to fix later. Newest first.

## Claude tabs accumulate in a card window's restored UI state

**Observed:** 2 Jul 2026 (F5 in the concurrent-session operating model), on the hardening card.

**Symptom:** VS Code persists a workspace window's editor layout — including Claude extension
tabs — in per-workspace UI state, and restores those tabs (which start/resume sessions) on the
next open. Each board→launch round trip can add a tab (the resume URI, plus whatever was open
when the window last closed), so the count grows: the hardening card's window opened with
**three** Claude sessions running, only one intended.

**Why cardctl can't fix it:** cardctl regenerates the `.code-workspace` *file* on each launch,
but VS Code's per-workspace UI state is separate and not something cardctl controls, so stale
tabs can't be pruned from outside.

**RESOLVED 8 Aug 2026 (#64) — and this entry had the diagnosis backwards.** The dominant cause
wasn't VS Code hoarding tabs; it was `cardctl launch` firing the resume URI *on top of* VS Code's
own restore, so every launch opened a second tab of the same session. Steve's experiment isolated
it: quit with one session open, reopen the workspace by hand → one session; launch the same card
from the board → two. `launch` now fires the URI only when there is nothing to restore (`--new`,
`--resume`, or a workspace it has never opened), so a relaunch reproduces what you left.

What remains isn't a bug: VS Code restores the tabs *you* left open — tidy them before closing a
card window if you don't want them back. The "close stray tabs after every launch" habit this
entry recommended is no longer needed, and it masked the real defect for five weeks.

## A normal relaunch doesn't disarm a running window

**Observed:** 2 Jul 2026 (F2 in the concurrent-session operating model).

**Symptom:** the generated `<card>.code-workspace` is meant to be the source of truth for "is
this window dangerous", but a normal `launch` regenerates the file **without** the dangerous
keys while the already-running window's extension keeps bypass armed. Seen live: the on-disk
workspace file showed a plain launch, yet bypass was active in the session. So "relaunch normal
to make a window safe again" does not work — the extension's armed state outlives the file that
set it. To truly reset, close the window and relaunch.

**Status:** mostly moot since slice 9 (launches are arm-only and never force bypass; each tab's
mode is dialled by hand), but the general rule stands: the workspace file describes the *next*
window, not the running one.

## Resume URI can land in the wrong (focused) VS Code window

**Observed:** 1 Jul 2026, launching the Japan trip card from the board.

**Symptom:** On the first launch attempt, `cardctl launch` started / resumed the Claude
session in the **currently-focused** VS Code window (the unrelated card-model-skill
workspace) instead of the card's own workspace window. A second attempt targeted the
correct window and resumed fine.

**Likely root cause:** the Claude resume URI (`vscode://anthropic.claude-code/open?session=<id>`)
has **no window-targeting parameter** (already noted in `build_workspace`). `cardctl launch`
opens the card's workspace via `code <ws>` and then fires the URI; if the freshly-opened
window hasn't taken focus yet, VS Code routes the URI to whatever window is currently
focused. So a race between "workspace window gains focus" and "URI fires" can drop the
session into the wrong instance.

**Steve's framing:** the launcher tries to find the correct workspace/VSC instance, fails,
and falls back to applying the change to the window in focus.

**Mitigated (2 Jul 2026, slice 4 / ai-skills#23):** `launch` now polls Hammerspoon (up to
`--delay`s, default 3) until the card's slugged window is open **and frontmost**, raising it
by window id if it opens without focus, and only then fires the URI. On timeout it exits
without firing (retry / raise `--delay` / `--no-poll` for the old behaviour); when
Hammerspoon is unavailable it falls back to the old fixed-delay-then-fire, with a note.

**RESOLVED 8 Aug 2026 (#64) by removing the URI from the common path** rather than making the
race safer. A plain relaunch now fires no URI at all, so there is nothing to mis-target, and it
skips the frontmost-polling entirely. The polling survives only where a URI is still deliberately
fired (`--new`, `--resume`, first launch of a workspace) — which is where it was always justified.

**Formerly — residual gap:** the URI itself still has no window-targeting parameter, so the
polling was best-effort narrowing, not a full solve — focus could change in the instant between
the frontmost check and URI delivery, and the `--no-poll` / hs-unavailable paths kept the
original race. Per F4 in the concurrent-session operating model, the priority of a full
solve has dropped: in the one-window-per-card model you mostly open tabs in an existing
window rather than racing a fresh one.
