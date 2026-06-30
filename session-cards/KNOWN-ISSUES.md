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

**Fix ideas (later):**
- Ensure/await the new workspace window is frontmost before firing the resume URI (poll via
  Hammerspoon window enumeration — `hs_code_windows()` already exists).
- Or open the workspace and only then dispatch the URI with a focus check/retry.
- Investigate whether VS Code offers any per-window URI routing.
