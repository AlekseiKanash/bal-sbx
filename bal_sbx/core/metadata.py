"""Persisted per-sandbox metadata."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SandboxMetadata:
    workspace: str
    created_at: str
    last_used_at: str
    agent: str | None = None

    def to_dict(self) -> dict:
        return {
            "workspace": self.workspace,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
            "agent": self.agent,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SandboxMetadata":
        return cls(
            workspace=data["workspace"],
            created_at=data["created_at"],
            last_used_at=data["last_used_at"],
            agent=data.get("agent"),
        )
