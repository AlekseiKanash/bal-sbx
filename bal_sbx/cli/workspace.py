"""Workspace inference for CLI commands.

Every CLI subcommand that operates on a workspace funnels through
`resolve_workspace`, so the discovery rules live in exactly one place.
"""

from __future__ import annotations

import os


def resolve_workspace(workspace: str | None, marker: str = ".bal/config.json") -> str:
    """Resolve the workspace root path.

    - If `workspace` is provided, canonicalize via `os.path.realpath` and return.
    - Otherwise walk upward from cwd looking for a `marker` file;
      fall back to cwd (canonicalized) if no marker is found.

    The marker is the per-workspace config file (`.bal/config.json`), not the
    `.bal/` directory itself, because `~/.bal/` is also the global config
    directory — matching the bare directory would resolve $HOME as the
    workspace for any cwd under it.
    """
    if workspace is not None:
        return os.path.realpath(workspace)

    cwd = os.path.realpath(os.getcwd())
    current = cwd
    while True:
        if os.path.isfile(os.path.join(current, marker)):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return cwd
        current = parent
