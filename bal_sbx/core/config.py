"""Sandbox config — env vars + shared tools.

The same schema is used both for the global defaults section of
`~/.bal/sandboxes.json` and for the per-sandbox `config` section. Per-sandbox
configs *replace* the global per key for env and per tool name for
shared_tools (no deep-merge).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from bal_sbx.core.errors import ConfigInvalid
from bal_sbx.core.shared_tools import SharedTool, parse_shared_tool


_EMPTY_ENV: Mapping[str, str] = MappingProxyType({})
_EMPTY_TOOLS: Mapping[str, SharedTool] = MappingProxyType({})


@dataclass(frozen=True)
class SandboxConfig:
    env: Mapping[str, str] = field(default_factory=lambda: _EMPTY_ENV)
    shared_tools: Mapping[str, SharedTool] = field(default_factory=lambda: _EMPTY_TOOLS)

    @classmethod
    def from_dict(cls, data: Mapping | None) -> "SandboxConfig":
        if data is None:
            return cls()
        if not isinstance(data, Mapping):
            raise ConfigInvalid("sandbox config must be an object")
        raw_env = data.get("env", {})
        if not isinstance(raw_env, Mapping):
            raise ConfigInvalid("sandbox config: 'env' must be an object")
        env: dict[str, str] = {}
        for k, v in raw_env.items():
            if not isinstance(k, str) or not isinstance(v, str):
                raise ConfigInvalid("sandbox config: env keys and values must be strings")
            env[k] = v
        raw_tools = data.get("shared_tools", {})
        if not isinstance(raw_tools, Mapping):
            raise ConfigInvalid("sandbox config: 'shared_tools' must be an object")
        tools: dict[str, SharedTool] = {}
        for name, entry in raw_tools.items():
            if not isinstance(name, str):
                raise ConfigInvalid("sandbox config: shared_tools keys must be strings")
            tools[name] = parse_shared_tool(name, entry)
        return cls(env=env, shared_tools=tools)

    def to_dict(self) -> dict:
        data: dict = {}
        if self.env:
            data["env"] = dict(self.env)
        if self.shared_tools:
            data["shared_tools"] = {
                name: tool.to_dict() for name, tool in self.shared_tools.items()
            }
        return data

    def merged_with(self, override: "SandboxConfig") -> "SandboxConfig":
        """Layer `override` on top of `self`. Replacement per key / per tool name."""
        return SandboxConfig(
            env={**self.env, **override.env},
            shared_tools={**self.shared_tools, **override.shared_tools},
        )
