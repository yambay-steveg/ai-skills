---
name: my-skill
description: >
  One-line description of what this skill does and when to trigger it.
  Include example phrases: "do X", "run Y", "check Z".
allowed-tools: Bash, Read, Write, Edit, Grep, Glob
---

# My Skill

## Overview

What this skill does and why it exists.

## Trigger

Use when:
- User says "do X"
- User says "run Y"

Do NOT use when:
- Unrelated scenario

## Instructions

Step-by-step instructions for Claude to follow when this skill is triggered.

1. Gather required inputs from the user
2. Run the script:
   ```bash
   python3 ~/.claude/skills/my-skill/scripts/main.py --arg value
   ```
3. Present the results

## Configuration

Any config files or environment variables the skill needs.

## Dependencies

- Python packages: `pip install package1 package2`
- System tools: e.g. pandoc, jq
