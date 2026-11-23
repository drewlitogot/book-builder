#!/bin/bash
# Double-click to open the Book Manager in your browser. (First time: right-click > Open, then Open.)
# Keep this Terminal window open while you work; press Quit in the page (or close this window) to stop.
cd "$(dirname "$0")/.." || exit 1
[ -x .venv/bin/python ] || { echo "Run 0-setup.command first."; read -n1; exit 1; }
.venv/bin/python tools/webapp.py
