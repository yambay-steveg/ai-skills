# cardctl — known issues

Running log of launcher/engine bugs to fix later. Newest first.

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

**Residual gap:** the URI itself still has no window-targeting parameter, so this is
best-effort narrowing, not a full solve — focus can still change in the instant between the
frontmost check and URI delivery, and the `--no-poll` / hs-unavailable paths keep the
original race. Per F4 in the concurrent-session operating model, the priority of a full
solve has dropped: in the one-window-per-card model you mostly open tabs in an existing
window rather than racing a fresh one.
