#!/bin/sh
# Build a launchable Book Builder for Linux (a folder with Python, Pandoc and Typst inside).
# Run ./Build_App_Linux.sh (or double-click it and choose Run in Terminal). The result is in dist/packages.
# To build for other systems too:  ./Build_App_Linux.sh --target all
cd "$(dirname "$0")" || exit 1
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY="$(command -v python3)"; fi
if [ -z "$PY" ]; then
  echo "Python 3.10 or newer (with pip) is needed to build. Install python3 and python3-pip from your package manager."
  exit 1
fi
"$PY" tools/package_app.py "$@"
CODE=$?
if [ $CODE -eq 0 ] && command -v xdg-open >/dev/null; then xdg-open dist/packages >/dev/null 2>&1 & fi
if [ -t 0 ]; then printf "Press Return to close. "; read -r _; fi
exit $CODE
