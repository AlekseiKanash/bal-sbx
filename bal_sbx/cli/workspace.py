"""Workspace inference for CLI commands.

Every CLI subcommand that operates on a workspace funnels through
`resolve_workspace`, so the discovery rules live in exactly one place.
"""

from __future__ import annotations

import os


def resolve_workspace(workspace: str | None, marker: str = ".bal") -> str:
    """Resolve the workspace root path.

    - If `workspace` is provided, canonicalize via `os.path.realpath` and return.
    - Otherwise walk upward from cwd looking for a `marker` directory;
      fall back to cwd (canonicalized) if no marker is found.
    """
    if workspace is not None:
        return os.path.realpath(workspace)

    cwd = os.path.realpath(os.getcwd())
    current = cwd
    while True:
        if os.path.isdir(os.path.join(current, marker)):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return cwd
        current = parent
