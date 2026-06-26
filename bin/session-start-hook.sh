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

Session-card context — this working folder maps to a card. Open with where it stands + what's next, and refresh the card's \`latest\` (and tick open actions) on wrap-up:
${card}"
  fi
fi

jq -n --arg msg "$msg" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $msg}}'
