#!/bin/bash
# Book Builder: Local Application Manager (macOS/Linux). Double-click in Finder, or run from Terminal.
# All the work is done by tools/manage.py; this only finds Python and starts it from this folder.
cd "$(dirname "$0")" || exit 1
if [ -x .venv/bin/python ]; then PY=.venv/bin/python
elif command -v python3 >/dev/null 2>&1; then PY=python3
else
  echo "Python 3.10 or newer is needed: install it from https://www.python.org/downloads/ and run this again."
  read -r -n1; exit 1
fi
exec "$PY" tools/manage.py "$@"
