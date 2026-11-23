#!/bin/bash
# Build a launchable Book Builder for macOS (Book Builder.app with Python, Pandoc and Typst inside).
# Double-click this file. The first time: right-click > Open. The result is in dist/packages.
# To build for other systems too:  ./Build_App_macOS.command --target all
cd "$(dirname "$0")" || exit 1
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY="$(command -v python3)"; fi
if [ -z "$PY" ]; then
  echo "Python 3.10 or newer is needed to build. Install it from https://www.python.org/downloads/"
  read -r -p "Press Return to close." _; exit 1
fi
"$PY" tools/package_app.py "$@"
CODE=$?
[ $CODE -eq 0 ] && open dist/packages
read -r -p "Press Return to close." _
exit $CODE
