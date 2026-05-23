"""Deterministic sandbox identity.

ID = "bal_" + blake2s(realpath(workspace), digest_size=3).hexdigest() — short, stable, collision-tolerant.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

from .paths import PathLayout


@dataclass(frozen=True)
class SandboxIdentity:
    id: str
    user: str
    workspace: str
    home: str
    workspace_link: str

    @classmethod
    def from_workspace(cls, workspace_path: str, layout: PathLayout) -> "SandboxIdentity":
        canonical = os.path.realpath(workspace_path)
        digest = hashlib.blake2s(canonical.encode(), digest_size=3).hexdigest()
        identity_id = f"bal_{digest}"
        return cls(
            id=identity_id,
            user=identity_id,
            workspace=canonical,
            home=layout.home_for(identity_id),
            workspace_link=layout.workspace_link_for(identity_id),
        )
