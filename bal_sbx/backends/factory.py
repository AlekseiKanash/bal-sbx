"""Backend factory — selects a Sandbox implementation by kind string."""

from __future__ import annotations

from bal_sbx.backends.base import Sandbox
from bal_sbx.backends.user import UserSandbox
from bal_sbx.core.identity import SandboxIdentity
from bal_sbx.system.ops import SystemOps


def build_sandbox(kind: str, identity: SandboxIdentity, system_ops: SystemOps) -> Sandbox:
    if kind == "user":
        return UserSandbox(identity, system_ops)
    raise ValueError(f"unknown sandbox kind: {kind!r}")
