"""Persisted per-sandbox metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from bal_sbx.core.config import SandboxConfig


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SandboxMetadata:
    workspace: str
    created_at: str
    last_used_at: str
    agent: str | None = None
    config: SandboxConfig = field(default_factory=SandboxConfig)

    def to_dict(self) -> dict:
        data: dict = {
            "workspace": self.workspace,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
            "agent": self.agent,
        }
        cfg = self.config.to_dict()
        if cfg:
            data["config"] = cfg
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "SandboxMetadata":
        return cls(
            workspace=data["workspace"],
            created_at=data["created_at"],
            last_used_at=data["last_used_at"],
            agent=data.get("agent"),
            config=SandboxConfig.from_dict(data.get("config")),
        )
