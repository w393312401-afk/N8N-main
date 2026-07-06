#!/bin/zsh
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

export LANG="en_US.UTF-8"
export LC_ALL="en_US.UTF-8"
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/local/sbin:$PATH"

VENV_PYTHON="$SCRIPT_DIR/.venv-mac/bin/python"

if [ -x "$VENV_PYTHON" ]; then
  "$VENV_PYTHON" launcher.py
  exit_code=$?

  if [ "$exit_code" -ne 0 ]; then
    echo
    echo "Launch failed while using .venv-mac."
    echo
    read -r "?Press Enter to close..."
  fi

  exit "$exit_code"
fi

find_supported_python() {
  local candidate
  for candidate in python3.13 python3.12 python3.11 python3.10 python3 python; do
    if ! command -v "$candidate" >/dev/null 2>&1; then
      continue
    fi
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

PYTHON_BIN="$(find_supported_python || true)"

if [ -n "$PYTHON_BIN" ]; then
  "$PYTHON_BIN" launcher.py
  exit_code=$?
else
  echo
  echo "Launch failed. No supported Python interpreter was found."
  if command -v python3 >/dev/null 2>&1; then
    echo "Detected python3: $(python3 --version 2>&1)"
  fi
  echo "Install Python 3.10+ and make sure it is in PATH, then run this launcher again."
  echo
  read -r "?Press Enter to close..."
  exit 1
fi

if [ "$exit_code" -ne 0 ]; then
  echo
  echo "Launch failed. Check Python availability, dependencies, or port usage."
  echo
  read -r "?Press Enter to close..."
fi

exit "$exit_code"
