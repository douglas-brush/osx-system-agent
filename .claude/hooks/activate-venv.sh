#!/bin/bash
# Auto-activate project venv for Claude Code Bash tool calls
VENV_DIR="$(dirname "$0")/../../.venv"
if [ -d "$VENV_DIR" ] && [ -z "$VIRTUAL_ENV" ]; then
  source "$VENV_DIR/bin/activate"
fi
