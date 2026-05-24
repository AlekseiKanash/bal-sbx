#!/usr/bin/env bash
# Install or update bal-sbx: sets up .venv, installs editable, symlinks into ~/.local/bin.
# Safe to re-run -- idempotent. Override the target dir with BAL_SBX_BIN_DIR.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${REPO_DIR}/.venv"
BIN_DIR="${BAL_SBX_BIN_DIR:-${HOME}/.local/bin}"
LINK_PATH="${BIN_DIR}/bal-sbx"

if [[ ! -d "$VENV_DIR" ]]; then
  echo "creating venv at ${VENV_DIR}"
  python3 -m venv "$VENV_DIR"
fi

echo "syncing package + dev deps (editable)"
"${VENV_DIR}/bin/pip" install --quiet --upgrade pip
"${VENV_DIR}/bin/pip" install --quiet -e "${REPO_DIR}[dev]"

mkdir -p "$BIN_DIR"
ln -sfn "${VENV_DIR}/bin/bal-sbx" "$LINK_PATH"
echo "linked ${LINK_PATH} -> ${VENV_DIR}/bin/bal-sbx"

case ":${PATH}:" in
  *":${BIN_DIR}:"*) ;;
  *)
    echo
    echo "note: ${BIN_DIR} is not on \$PATH"
    echo "add to ~/.zshrc (or ~/.bashrc):"
    echo "  export PATH=\"${BIN_DIR}:\$PATH\""
    ;;
esac

echo
echo "done. try: bal-sbx --help"
