#!/usr/bin/env bash
# Sandbox probe — captures execution context to out.log in the workspace.

set -u

OUT="$(dirname "$0")/out.log"

{
  echo "=== bal-sbx probe @ $(date -u +%FT%TZ) ==="
  echo
  echo "--- identity ---"
  echo "whoami: $(whoami)"
  echo "id:     $(id)"
  echo
  echo "--- working dir ---"
  echo "pwd:    $(pwd)"
  echo "\$PWD:   ${PWD:-<unset>}"
  echo "script: $0"
  echo "argv:   $*"
  echo
  echo "--- home + shell ---"
  echo "\$HOME:  ${HOME:-<unset>}"
  echo "\$USER:  ${USER:-<unset>}"
  echo "\$SHELL: ${SHELL:-<unset>}"
  echo "\$PATH:  ${PATH:-<unset>}"
  echo
  echo "--- full environment ---"
  env | sort
  echo
  echo "--- workspace write probe ---"
  marker="$(dirname "$0")/.probe_marker.$$"
  if echo "written by $(whoami) at $(date -u +%FT%TZ)" > "$marker" 2>/dev/null; then
    echo "workspace write: OK ($marker)"
    rm -f "$marker"
  else
    echo "workspace write: DENIED"
  fi
  echo
  echo "--- host-home read probe ---"
  if ls /Users/akanash/.ssh >/dev/null 2>&1; then
    echo "host ~/.ssh read: VISIBLE (sandbox NOT isolating)"
  else
    echo "host ~/.ssh read: blocked (good — credential isolation working)"
  fi
  echo
  echo "=== end probe ==="
} > "$OUT" 2>&1

echo "wrote $OUT"
