"""Public facade for bal-sbx.

`SandboxManager` is the only public class — everything else under `bal_sbx`
is implementation detail. Typical use::

    from bal_sbx import SandboxManager, SandboxMode
    launcher = SandboxManager().launcher(workspace, mode=SandboxMode.SAFE)
    launcher.exec_replace(["agent", *args])

The constructor's ``system_ops`` parameter exists so tests can inject a fake;
production callers leave it `None` and let the manager call
:meth:`SystemOps.detect` itself. ``settings`` defaults to
:meth:`Settings.load` so the global TOML (if any) is honored automatically.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from bal_sbx.backends.base import Sandbox
from bal_sbx.backends.factory import build_sandbox
from bal_sbx.backends.user import UserSandbox
from bal_sbx.config.settings import Settings
from bal_sbx.config.workspace import WorkspaceConfig
from bal_sbx.core.errors import SandboxNotFound
from bal_sbx.core.identity import SandboxIdentity
from bal_sbx.core.metadata import SandboxMetadata
from bal_sbx.core.paths import PathLayout
from bal_sbx.core.staleness import StaleReport, detect_stale
from bal_sbx.core.status import SandboxStatus
from bal_sbx.exec.launcher import AgentLauncher, DirectLauncher, SandboxedLauncher
from bal_sbx.registry.json_file import JsonFileRegistry
from bal_sbx.system.ops import SystemOps


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SandboxMode(str, Enum):
    SAFE = "safe"
    UNSAFE = "unsafe"


@dataclass(frozen=True)
class Capabilities:
    platform: str
    can_sudo: bool
    acl_supported: bool
    unsupported_reason: str | None


class SandboxManager:
    def __init__(
        self,
        system_ops: SystemOps | None = None,
        registry: JsonFileRegistry | None = None,
        path_layout: PathLayout | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings if settings is not None else Settings.load()
        self._path_layout = path_layout if path_layout is not None else PathLayout.default()
        self._system_ops = (
            system_ops
            if system_ops is not None
            else SystemOps.detect(self._settings.privilege_mode)
        )
        self._registry = (
            registry
            if registry is not None
            else JsonFileRegistry(
                self._settings.registry_path or self._path_layout.registry_path
            )
        )

    def capabilities(self) -> Capabilities:
        return Capabilities(
            platform=sys.platform,
            can_sudo=self._system_ops.privilege.is_available(),
            acl_supported=self._system_ops.acl.is_supported(),
            unsupported_reason=SystemOps.unsupported_reason(),
        )

    def resolve(self, workspace_path: str) -> SandboxIdentity:
        return SandboxIdentity.from_workspace(workspace_path, self._path_layout)

    def get_or_create(self, workspace_path: str, kind: str = "user") -> Sandbox:
        identity = self.resolve(workspace_path)
        sandbox = build_sandbox(kind, identity, self._system_ops)
        sandbox.create()
        if self._registry.get(identity.id) is None:
            now = _now_iso()
            self._registry.put(
                identity.id,
                SandboxMetadata(
                    workspace=identity.workspace,
                    created_at=now,
                    last_used_at=now,
                ),
            )
        else:
            self._registry.touch(identity.id)
        return sandbox

    def launcher(
        self,
        workspace_path: str,
        mode: SandboxMode = SandboxMode.SAFE,
    ) -> AgentLauncher:
        if mode is SandboxMode.UNSAFE:
            return DirectLauncher()
        sandbox = self.get_or_create(workspace_path)
        workspace_config = WorkspaceConfig(
            sandbox.identity.workspace, self._path_layout
        )
        return SandboxedLauncher(
            sandbox,
            self._system_ops,
            self._registry,
            denylist=self._settings.env_denylist,
            workspace_config=workspace_config,
        )

    def unsafe(self, workspace_path: str) -> AgentLauncher:
        return self.launcher(workspace_path, mode=SandboxMode.UNSAFE)

    def list(self) -> list[tuple[SandboxIdentity, SandboxMetadata, SandboxStatus]]:
        results: list[tuple[SandboxIdentity, SandboxMetadata, SandboxStatus]] = []
        for _sid, meta in self._registry.list():
            identity = SandboxIdentity.from_workspace(meta.workspace, self._path_layout)
            sandbox = UserSandbox(identity, self._system_ops)
            results.append((identity, meta, sandbox.status()))
        results.sort(key=lambda triple: triple[1].last_used_at, reverse=True)
        return results

    def destroy(self, workspace_path: str) -> None:
        identity = self.resolve(workspace_path)
        if self._registry.get(identity.id) is None:
            raise SandboxNotFound(identity.id)
        sandbox = build_sandbox("user", identity, self._system_ops)
        sandbox.destroy()
        self._registry.delete(identity.id)

    def _reports(self) -> list[StaleReport]:
        reports: list[StaleReport] = []
        for _sid, meta in self._registry.list():
            identity = SandboxIdentity.from_workspace(meta.workspace, self._path_layout)
            reports.append(detect_stale(identity, meta, self._system_ops))
        return reports

    def repair_all(self, dry_run: bool = False) -> list[StaleReport]:
        reports = [r for r in self._reports() if r.statuses]
        if dry_run:
            return reports
        for report in reports:
            if SandboxStatus.MISSING_WORKSPACE in report.statuses:
                continue
            if SandboxStatus.INVALID_METADATA in report.statuses:
                continue
            sandbox = UserSandbox(report.identity, self._system_ops)
            sandbox.repair()
        return reports

    def cleanup_stale(self, dry_run: bool = False) -> list[StaleReport]:
        candidates = [r for r in self._reports() if not r.recoverable]
        if dry_run:
            return candidates
        for report in candidates:
            sandbox = UserSandbox(report.identity, self._system_ops)
            sandbox.destroy()
            self._registry.delete(report.identity.id)
        return candidates
