#!/bin/bash
# Install a skill from this repo to ~/.claude/skills/
#
# Usage: ./install.sh <skill-name>
# Example: ./install.sh my-skill
#
# This copies the skill folder to ~/.claude/skills/<skill-name>/
# Restart your Claude Code session after installing.

set -euo pipefail

SKILLS_DIR="$HOME/.claude/skills"
REPO_SKILLS_DIR="$(cd "$(dirname "$0")" && pwd)/skills"

if [ $# -eq 0 ]; then
    echo "Usage: $0 <skill-name>"
    echo ""
    echo "Available skills:"
    for dir in "$REPO_SKILLS_DIR"/*/; do
        name=$(basename "$dir")
        [ "$name" = "_template" ] && continue
        echo "  $name"
    done
    exit 1
fi

SKILL_NAME="$1"
SOURCE="$REPO_SKILLS_DIR/$SKILL_NAME"

if [ ! -d "$SOURCE" ]; then
    echo "Error: Skill '$SKILL_NAME' not found in $REPO_SKILLS_DIR/"
    exit 1
fi

if [ "$SKILL_NAME" = "_template" ]; then
    echo "Error: Cannot install the template. Copy it first:"
    echo "  cp -r skills/_template skills/my-new-skill"
    exit 1
fi

DEST="$SKILLS_DIR/$SKILL_NAME"

if [ -d "$DEST" ]; then
    echo "Skill '$SKILL_NAME' already installed at $DEST"
    read -p "Overwrite? [y/N] " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        echo "Aborted."
        exit 0
    fi
    rm -rf "$DEST"
fi

mkdir -p "$SKILLS_DIR"
cp -r "$SOURCE" "$DEST"
echo "Installed '$SKILL_NAME' to $DEST"
echo "Restart your Claude Code session to load the skill."
