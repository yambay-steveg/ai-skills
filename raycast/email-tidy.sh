#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Email Tidy
# @raycast.mode fullOutput
# @raycast.packageName Email Tools

# Optional parameters:
# @raycast.icon 📧
# @raycast.description Tidy all email - SaneBox triage via Claude Code
# @raycast.needsConfirmation false

cd ~/ai-skills
open -a Terminal.app
osascript -e 'tell application "Terminal" to do script "cd ~/ai-skills && claude \"tidy my email\""'
