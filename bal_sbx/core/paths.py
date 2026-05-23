"""Centralized path layout (A5). Everything else accepts a PathLayout."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from .errors import PlatformUnsupported


@dataclass(frozen=True)
class PathLayout:
    home_root: str
    registry_path: str
    workspace_config_dir: str = ".bal"
    workspace_config_file: str = ".bal/config.json"

    @classmethod
    def default(cls) -> "PathLayout":
        if sys.platform == "darwin":
            home_root = "/Users"
        elif sys.platform.startswith("linux"):
            home_root = "/home"
        else:
            raise PlatformUnsupported(f"unsupported platform: {sys.platform}")
        registry_path = os.path.expanduser("~/.bal/sandboxes.json")
        return cls(home_root=home_root, registry_path=registry_path)

    def home_for(self, identity_id: str) -> str:
        return os.path.join(self.home_root, identity_id)

    def workspace_link_for(self, identity_id: str) -> str:
        return os.path.join(self.home_for(identity_id), "workspace")
