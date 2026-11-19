#!/bin/bash
# Double-click this file to start the Boo0om home server on a Mac.
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python is not installed yet."
  echo "Install it from https://www.python.org/downloads/ and double-click this file again."
  open "https://www.python.org/downloads/"
  read -r -p "Press Return to close."
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "First start: setting things up. This takes a minute and needs the internet."
  python3 -m venv .venv || { read -r -p "Could not set up Python. Press Return to close."; exit 1; }
fi
.venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt \
  || { read -r -p "Could not download what the server needs. Check your internet and try again. Press Return to close."; exit 1; }

echo "Starting. Leave this window open while you listen; close it to stop the server."
OPEN_BROWSER=1 DEMO="${DEMO:-1}" .venv/bin/python server.py
read -r -p "The server stopped. Press Return to close."
