#!/bin/bash
# The older pop-up dialog menu. The Book Manager (browser page) replaces it.
cd "$(dirname "$0")/.." || exit 1
[ -x .venv/bin/python ] || { echo "Run 0-setup.command first."; read -n1; exit 1; }
.venv/bin/python tools/menu.py
osascript -e 'tell application "Terminal" to close (every window whose name contains "Old menu.command")' >/dev/null 2>&1 &
exit 0
