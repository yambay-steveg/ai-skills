# ai-skills

Personal repository for building, testing, and sharing Claude Code skills.

## Repo Structure

```
skills/
  _template/          # Copy this to start a new skill
    SKILL.md          # Claude Code loads this (YAML frontmatter + instructions)
    scripts/          # Python/shell scripts the skill calls
    tests/            # Tests for the scripts
  my-skill/           # Your custom skills go here
    SKILL.md
    scripts/
    tests/
profiles/             # Notes on third-party skills under evaluation
install.sh            # Install a skill to ~/.claude/skills/
```

## Creating a New Skill

1. Copy the template:
   ```bash
   cp -r skills/_template skills/my-new-skill
   ```
2. Edit `skills/my-new-skill/SKILL.md` — set name, description, trigger phrases, and instructions
3. Add any Python scripts to `scripts/` and tests to `tests/`
4. Test locally: `pytest skills/my-new-skill/tests/`
5. Install: `./install.sh my-new-skill`
6. Restart Claude Code to load the skill

## SKILL.md Format

```yaml
---
name: my-skill
description: >
  One-line description and trigger phrases.
allowed-tools: Bash, Read, Write, Edit, Grep, Glob
---

# Instructions for Claude follow here...
```

The `description` field tells Claude when to trigger the skill. The body contains step-by-step instructions Claude follows.

## Installing a Skill

```bash
./install.sh <skill-name>
```

This copies the skill folder to `~/.claude/skills/<skill-name>/`. Restart your Claude Code session after installing.

## Third-Party Skills

Leon's skills (md-to-word, files, email) are documented in `profiles/leon.md`. These are installed separately from SharePoint — see CLAUDE.md for details.
