#!/bin/zsh
# Claude Code SessionStart hook.
# 1. AWST time context (always).
# 2. If the session's cwd maps to a session-card, inject that card's status/latest/
#    open-actions so the session lands card-aware (and the card link self-caches).
# Source of truth: ai-skills/bin/session-start-hook.sh — synced to ~/bin/session-start-hook.sh.
# Wired in ~/.claude/settings.json under hooks.SessionStart.

input=$(cat 2>/dev/null)
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)

dt=$(TZ='Australia/Perth' date '+%Y-%m-%d %H:%M')
dow=$(TZ='Australia/Perth' date '+%A')
msg="Current time: ${dt} AWST (${dow}). Steve works in AWST (UTC+8) — convert all timestamps (Jira, git, calendar, email) to AWST before reporting, bucketing by day, or quoting times. Display times as AWST unless asked otherwise."

if [ -n "$cwd" ]; then
  card=$(/Users/steve/bin/cardctl which "$cwd" --record --quiet 2>/dev/null)
  if [ -n "$card" ]; then
    msg="${msg}

Session-card context — this working folder maps to a card (shown below). Open with where it stands + what's next.
${card}

Card conventions (don't hand-invent fields): on wrap, record this session — run \`cardctl link <card-path-above> --current\`, then add a one-line note under the card's \`## Sessions\` heading (what this session did). Refresh \`latest\` (current state / next step); set \`status\` to one of backlog | in-progress | on-hold | done | archived (\`done\` clears the board but keeps the folder; \`archived\` files it). \`sessionId\` = current pin; \`## Sessions\` (body) = the readable history. Full how-to: ai-skills/session-cards/cardctl.md and the work vault Procedures/session-card-system.md note."
  fi
fi

jq -n --arg msg "$msg" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $msg}}'
