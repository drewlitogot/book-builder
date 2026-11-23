#!/bin/bash
# One-time setup: installs Pandoc and Typst (via Homebrew) and the Python packages.
cd "$(dirname "$0")/.." || exit 1
command -v brew >/dev/null || { echo "Install Homebrew first: https://brew.sh"; read -n1; exit 1; }
brew install pandoc typst
python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt && echo "Setup done."
echo; read -n1 -p "Press any key to close."
