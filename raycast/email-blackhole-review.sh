#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title BlackHole Review
# @raycast.mode fullOutput
# @raycast.packageName Email Tools

# Optional parameters:
# @raycast.icon 🕳️
# @raycast.description Safety check SaneBlackHole for interesting emails via Claude Code
# @raycast.needsConfirmation false

open -a Terminal.app
osascript -e 'tell application "Terminal" to do script "cd ~/ai-skills && claude \"blackhole review\""'
