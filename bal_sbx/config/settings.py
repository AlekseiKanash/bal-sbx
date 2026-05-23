"""Global settings loaded from `~/.bal/sbx.toml`.

Read-only at runtime. Precedence (CLI > workspace > global > defaults) is
enforced by the consumer; this module only owns the "global" layer.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass

from bal_sbx.core.errors import ConfigInvalid
from bal_sbx.exec.environment import DEFAULT_DENYLIST


DEFAULT_SETTINGS_PATH = "~/.bal/sbx.toml"


@dataclass(frozen=True)
class Settings:
    privilege_mode: str = "cached"
    env_denylist: tuple[str, ...] = DEFAULT_DENYLIST
    registry_path: str | None = None

    @classmethod
    def load(cls, path: str | None = None) -> "Settings":
        target = os.path.expanduser(path if path is not None else DEFAULT_SETTINGS_PATH)
        if not os.path.exists(target):
            return cls()
        with open(target, "rb") as f:
            data = tomllib.load(f)
        known = {"privilege_mode", "env_denylist", "registry_path"}
        for key in data:
            if key not in known:
                raise ConfigInvalid(f"unknown setting: {key}")
        kwargs: dict = {}
        if "privilege_mode" in data:
            kwargs["privilege_mode"] = data["privilege_mode"]
        if "env_denylist" in data:
            kwargs["env_denylist"] = tuple(data["env_denylist"])
        if "registry_path" in data:
            kwargs["registry_path"] = data["registry_path"]
        return cls(**kwargs)
