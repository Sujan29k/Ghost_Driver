#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WINDOWS_SCRIPT="$ROOT_DIR/start.ps1"

if ! command -v powershell.exe >/dev/null 2>&1; then
  echo "This launcher starts the Windows CARLA simulator and requires Windows PowerShell."
  echo "Run start.ps1 on the CARLA Windows machine, or use Git Bash with PowerShell available."
  exit 1
fi

if command -v cygpath >/dev/null 2>&1; then
  WINDOWS_SCRIPT="$(cygpath -w "$WINDOWS_SCRIPT")"
elif command -v wslpath >/dev/null 2>&1; then
  WINDOWS_SCRIPT="$(wslpath -w "$WINDOWS_SCRIPT")"
fi

echo "Starting Ghost Driver, CARLA, the Python gateway, and RAFT..."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$WINDOWS_SCRIPT" "$@"
