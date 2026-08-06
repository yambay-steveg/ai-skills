#!/bin/zsh
# Claude Code SessionStart hook.
# 1. Time context — home timezone, or a travel timezone while a trip is running.
# 2. If the session's cwd maps to a session-card, inject that card's status/latest/
#    open-actions so the session lands card-aware (and the card link self-caches).
# Source of truth: ai-skills/bin/session-start-hook.sh — synced to ~/bin/session-start-hook.sh.
# Wired in ~/.claude/settings.json under hooks.SessionStart.

input=$(cat 2>/dev/null)
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)

# ── Timezone ────────────────────────────────────────────────────────────────────
# Sessions must report Steve's *current* local time, not his home time, or every
# day-bucketed summary lands on the wrong day while he's away.
#
# To declare a trip, set both values below (or export them for a one-off) — the trip
# then expires by itself, so a forgotten edit can't leave sessions reporting the wrong
# zone for months:
#   TRAVEL_TZ='Europe/London'   # IANA zone while away
#   TRAVEL_UNTIL='2026-08-05'   # last day away, INCLUSIVE; reverts home the next day
# Leave TRAVEL_TZ empty when home. Both are overridable from the environment, so a
# trip can be simulated (and tested) without editing this file.
HOME_TZ="${HOME_TZ:-Australia/Perth}"
TRAVEL_TZ="${TRAVEL_TZ:-}"
TRAVEL_UNTIL="${TRAVEL_UNTIL:-}"

tz="$HOME_TZ"
away=0
if [ -n "$TRAVEL_TZ" ] && [ -n "$TRAVEL_UNTIL" ]; then
  # Lexicographic compare is correct for ISO-8601 dates, and needs no date parsing.
  # Evaluated in the travel zone, so the revert happens on Steve's local midnight.
  if [[ "$(TZ="$TRAVEL_TZ" date '+%Y-%m-%d')" < "$TRAVEL_UNTIL" || \
        "$(TZ="$TRAVEL_TZ" date '+%Y-%m-%d')" == "$TRAVEL_UNTIL" ]]; then
    tz="$TRAVEL_TZ"
    away=1
  fi
fi

dt=$(TZ="$tz" date '+%Y-%m-%d %H:%M')
dow=$(TZ="$tz" date '+%A')
zone=$(TZ="$tz" date '+%Z')
off=$(TZ="$tz" date '+%z')
if [ "$away" -eq 1 ]; then
  where="Steve is travelling (${TRAVEL_TZ}) until ${TRAVEL_UNTIL}, so report local time (${zone}, UTC${off})"
else
  where="Steve works in ${zone} (UTC${off})"
fi
msg="Current time: ${dt} ${zone} (${dow}). ${where} — convert all timestamps (Jira, git, calendar, email) to ${zone} before reporting, bucketing by day, or quoting times. Display times as ${zone} unless asked otherwise."

if [ -n "$cwd" ]; then
  card=$(/Users/steve/bin/cardctl which "$cwd" --record --quiet 2>/dev/null)
  if [ -n "$card" ]; then
    msg="${msg}

Session-card context — this working folder maps to a card (shown below). Open with where it stands + what's next.
${card}

Card conventions — **cardctl is the single validated writer; do NOT hand-edit card frontmatter.** Change fields via cardctl: \`set-status\` (status) and \`set\` (area/program/raised-at/tags/summary). **\"Add a folder\" (a repo, a monorepo worktree) means \`cardctl set <card> --add-path <folder>\`** — never VS Code's Add Folder to Workspace: the \`.code-workspace\` is generated from the card's \`paths\` and regenerated on every launch, so window-side additions are silently discarded. \`--remove-path\` to drop one. On wrap: \`cardctl link <card-path-above> --current\`, then add a one-line note under \`## Sessions\` (what this session did). Only \`latest\` and the \`## Sessions\` note lack a cardctl writer for now — edit those two minimally by hand; everything else goes through cardctl. **Rename notes/cards only via the Obsidian API** (\`obsidian rename …\`), never shell/git, or links break. Status vocab: backlog | in-progress | on-hold | done | archived (\`done\` clears the board, keeps the folder; \`archived\` files it) — never set \`done\`/\`archived\` without Steve's say-so. Full model + rules: work vault Procedures/session-card-system.md; commands: ai-skills/session-cards/cardctl.md."
  fi
fi

jq -n --arg msg "$msg" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $msg}}'
