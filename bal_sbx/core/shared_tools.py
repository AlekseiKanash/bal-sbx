"""Shared host tool definitions.

A `SharedTool` describes a host-installed binary/library tree that the user
has opted to expose into a sandbox. The dataclass is pure data — validation
happens in `__post_init__` and the only "smart" method, `path_entries`, is
purely string-based (no filesystem I/O).

The serialization shape (used by both the registry's `global` section and
each per-sandbox `config` section) is:

    {
      "paths": ["/abs/path", ...],
      "permissions": ["read", "execute", ...],
      "env": {"KEY": "value", ...}    # optional
    }

`permissions` vocabulary: read, execute, write, env. The first three map to
filesystem ACL rights; `env` is informational. The `env` field on a tool is
honored whenever present, regardless of whether `env` is listed in
`permissions`.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum

from bal_sbx.core.errors import ConfigInvalid


class Permission(str, Enum):
    READ = "read"
    EXECUTE = "execute"
    WRITE = "write"
    ENV = "env"


@dataclass(frozen=True)
class SharedTool:
    name: str
    paths: tuple[str, ...]
    permissions: frozenset[Permission]
    env: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ConfigInvalid("shared tool name cannot be empty")
        if not self.paths:
            raise ConfigInvalid(f"shared tool {self.name!r}: paths cannot be empty")
        for p in self.paths:
            if not p or not os.path.isabs(p):
                raise ConfigInvalid(
                    f"shared tool {self.name!r}: paths must be absolute, got {p!r}"
                )
        if not self.permissions:
            raise ConfigInvalid(
                f"shared tool {self.name!r}: permissions cannot be empty"
            )
        if (Permission.EXECUTE in self.permissions or Permission.WRITE in self.permissions) \
                and Permission.READ not in self.permissions:
            raise ConfigInvalid(
                f"shared tool {self.name!r}: 'read' is required when 'execute' or 'write' is granted"
            )

    @property
    def acl_permissions(self) -> frozenset[Permission]:
        """ACL-relevant subset (read/execute/write) — drops `env`."""
        return frozenset(p for p in self.permissions if p is not Permission.ENV)

    def path_entries(self) -> list[str]:
        """Paths that should be prepended to the sandbox PATH.

        Pure string heuristic: a path goes on PATH iff it (a) ends in `/bin`
        or (b) its parent directory ends in `/bin` (single-binary specs like
        `/usr/local/bin/python3.11`). Other paths are ACL-only.
        """
        seen: set[str] = set()
        entries: list[str] = []
        for p in self.paths:
            normalized = p.rstrip("/") or "/"
            candidate: str | None = None
            if normalized.endswith("/bin"):
                candidate = normalized
            else:
                parent = os.path.dirname(normalized)
                if parent.endswith("/bin"):
                    candidate = parent
            if candidate and candidate not in seen:
                seen.add(candidate)
                entries.append(candidate)
        return entries

    def to_dict(self) -> dict:
        data: dict = {
            "paths": list(self.paths),
            "permissions": [p.value for p in sorted(self.permissions, key=lambda x: x.value)],
        }
        if self.env:
            data["env"] = dict(self.env)
        return data


def parse_shared_tool(name: str, data: Mapping) -> SharedTool:
    """Build a `SharedTool` from a JSON-decoded mapping. Raises `ConfigInvalid`."""
    if not isinstance(data, Mapping):
        raise ConfigInvalid(f"shared tool {name!r}: entry must be an object")
    raw_paths = data.get("paths")
    if raw_paths is None:
        raise ConfigInvalid(f"shared tool {name!r}: missing 'paths'")
    if not isinstance(raw_paths, (list, tuple)) or any(not isinstance(p, str) for p in raw_paths):
        raise ConfigInvalid(f"shared tool {name!r}: 'paths' must be a list of strings")
    raw_perms = data.get("permissions")
    if raw_perms is None:
        raise ConfigInvalid(f"shared tool {name!r}: missing 'permissions'")
    if not isinstance(raw_perms, (list, tuple)):
        raise ConfigInvalid(f"shared tool {name!r}: 'permissions' must be a list")
    permissions: set[Permission] = set()
    for p in raw_perms:
        if not isinstance(p, str):
            raise ConfigInvalid(f"shared tool {name!r}: permission values must be strings")
        try:
            permissions.add(Permission(p))
        except ValueError as exc:
            raise ConfigInvalid(
                f"shared tool {name!r}: unknown permission {p!r}"
            ) from exc
    raw_env = data.get("env", {})
    if not isinstance(raw_env, Mapping):
        raise ConfigInvalid(f"shared tool {name!r}: 'env' must be an object")
    env = {}
    for k, v in raw_env.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise ConfigInvalid(f"shared tool {name!r}: env keys and values must be strings")
        env[k] = v
    return SharedTool(
        name=name,
        paths=tuple(raw_paths),
        permissions=frozenset(permissions),
        env=env,
    )
