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

Card conventions — **cardctl is the single validated writer; do NOT hand-edit card frontmatter.** Change fields via cardctl: \`set-status\` (status) and \`set\` (area/program/raised-at/tags). On wrap: \`cardctl link <card-path-above> --current\`, then add a one-line note under \`## Sessions\` (what this session did). Only \`latest\` and the \`## Sessions\` note lack a cardctl writer for now — edit those two minimally by hand; everything else goes through cardctl. **Rename notes/cards only via the Obsidian API** (\`obsidian rename …\`), never shell/git, or links break. Status vocab: backlog | in-progress | on-hold | done | archived (\`done\` clears the board, keeps the folder; \`archived\` files it) — never set \`done\`/\`archived\` without Steve's say-so. Full model + rules: work vault Procedures/session-card-system.md; commands: ai-skills/session-cards/cardctl.md."
  fi
fi

jq -n --arg msg "$msg" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $msg}}'
