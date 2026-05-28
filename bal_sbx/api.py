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

import json
import os
import sys
import warnings
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum

from bal_sbx.backends.base import Sandbox
from bal_sbx.backends.factory import build_sandbox
from bal_sbx.backends.user import ToolGrant, UserSandbox
from bal_sbx.config.settings import Settings
from bal_sbx.core.config import SandboxConfig
from bal_sbx.core.errors import SandboxNotFound
from bal_sbx.core.identity import SandboxIdentity
from bal_sbx.core.metadata import SandboxMetadata
from bal_sbx.core.paths import PathLayout
from bal_sbx.core.shared_tools import SharedTool
from bal_sbx.core.staleness import StaleReport, detect_stale
from bal_sbx.core.status import SandboxStatus
from bal_sbx.exec.launcher import AgentLauncher, DirectLauncher, SandboxedLauncher
from bal_sbx.registry.json_file import JsonFileRegistry
from bal_sbx.system.ops import SystemOps

# Legacy per-workspace env file from step 12. Read-only here (auto-migrated
# into the registry on first `get_or_create`); never written by this code.
_LEGACY_WORKSPACE_CONFIG = os.path.join(".bal", "config.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_legacy_workspace_env(workspace: str) -> dict[str, str]:
    path = os.path.join(workspace, _LEGACY_WORKSPACE_CONFIG)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    env = data.get("env") if isinstance(data, dict) else None
    if not isinstance(env, dict):
        return {}
    return {k: v for k, v in env.items() if isinstance(k, str) and isinstance(v, str)}


def _filter_existing_paths(tool: SharedTool) -> list[str]:
    survivors: list[str] = []
    for p in tool.paths:
        if os.path.exists(p):
            survivors.append(p)
        else:
            warnings.warn(
                f"shared tool {tool.name!r}: path {p} not found, skipping",
                stacklevel=3,
            )
    return survivors


def _path_entries_for(paths: list[str]) -> list[str]:
    """Apply the bin-or-parent-bin heuristic to the *existing* paths only."""
    seen: set[str] = set()
    entries: list[str] = []
    for p in paths:
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


@dataclass(frozen=True)
class _ResolvedTooling:
    grants: tuple[ToolGrant, ...]
    path_entries: tuple[str, ...]
    env: dict[str, str]


def _resolve_tooling(config: SandboxConfig) -> _ResolvedTooling:
    all_grants: list[ToolGrant] = []
    all_paths: list[str] = []
    seen_paths: set[str] = set()
    env: dict[str, str] = {}
    for tool in config.shared_tools.values():
        existing = _filter_existing_paths(tool)
        if not existing:
            # Even if every path is missing, the tool's env still applies —
            # the user opted in explicitly.
            if tool.env:
                env.update(tool.env)
            continue
        acl_perms = tool.acl_permissions
        if acl_perms:
            for p in existing:
                all_grants.append(ToolGrant(path=p, permissions=acl_perms))
        for entry in _path_entries_for(existing):
            if entry not in seen_paths:
                seen_paths.add(entry)
                all_paths.append(entry)
        if tool.env:
            env.update(tool.env)
    return _ResolvedTooling(
        grants=tuple(all_grants),
        path_entries=tuple(all_paths),
        env=env,
    )


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

    def resolve_config(self, workspace_path: str) -> SandboxConfig:
        identity = self.resolve(workspace_path)
        metadata = self._registry.get(identity.id)
        per_sandbox = metadata.config if metadata is not None else SandboxConfig()
        return self._registry.global_config().merged_with(per_sandbox)

    def get_or_create(self, workspace_path: str, kind: str = "user") -> Sandbox:
        identity = self.resolve(workspace_path)
        metadata = self._ensure_metadata(identity)
        config = self._registry.global_config().merged_with(metadata.config)
        tooling = _resolve_tooling(config)
        sandbox = build_sandbox(kind, identity, self._system_ops, shared_tool_grants=tooling.grants)
        sandbox.create()
        self._registry.touch(identity.id)
        return sandbox

    def _ensure_metadata(self, identity: SandboxIdentity) -> SandboxMetadata:
        metadata = self._registry.get(identity.id)
        if metadata is None:
            legacy_env = _load_legacy_workspace_env(identity.workspace)
            config = SandboxConfig(env=legacy_env) if legacy_env else SandboxConfig()
            now = _now_iso()
            metadata = SandboxMetadata(
                workspace=identity.workspace,
                created_at=now,
                last_used_at=now,
                config=config,
            )
            self._registry.put(identity.id, metadata)
            return metadata
        if not metadata.config.env:
            legacy_env = _load_legacy_workspace_env(identity.workspace)
            if legacy_env:
                migrated = SandboxConfig(
                    env=legacy_env,
                    shared_tools=metadata.config.shared_tools,
                )
                metadata = replace(metadata, config=migrated)
                self._registry.put(identity.id, metadata)
        return metadata

    def update_config(
        self,
        workspace_path: str,
        mutate,
    ) -> SandboxConfig:
        """Apply `mutate(SandboxConfig) -> SandboxConfig` to the per-sandbox config.

        Creates a config-only registry entry if none exists. Returns the new
        per-sandbox config (not the merged view).
        """
        identity = self.resolve(workspace_path)
        metadata = self._registry.get(identity.id)
        if metadata is None:
            now = _now_iso()
            metadata = SandboxMetadata(
                workspace=identity.workspace,
                created_at=now,
                last_used_at=now,
            )
        new_config = mutate(metadata.config)
        metadata = replace(metadata, config=new_config)
        self._registry.put(identity.id, metadata)
        return new_config

    def launcher(
        self,
        workspace_path: str,
        mode: SandboxMode = SandboxMode.SAFE,
    ) -> AgentLauncher:
        if mode is SandboxMode.UNSAFE:
            return DirectLauncher()
        identity = self.resolve(workspace_path)
        metadata = self._ensure_metadata(identity)
        config = self._registry.global_config().merged_with(metadata.config)
        tooling = _resolve_tooling(config)
        sandbox = build_sandbox("user", identity, self._system_ops, shared_tool_grants=tooling.grants)
        sandbox.create()
        self._registry.touch(identity.id)
        return SandboxedLauncher(
            sandbox,
            self._system_ops,
            self._registry,
            denylist=self._settings.env_denylist,
            workspace_env=dict(config.env),
            shared_tool_paths=tooling.path_entries,
            shared_tool_env=tooling.env,
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
        metadata = self._registry.get(identity.id)
        if metadata is None:
            raise SandboxNotFound(identity.id)
        config = self._registry.global_config().merged_with(metadata.config)
        grants = _resolve_tooling(config).grants
        sandbox = build_sandbox("user", identity, self._system_ops, shared_tool_grants=grants)
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
            metadata = self._registry.get(report.identity.id)
            if metadata is None:
                continue
            config = self._registry.global_config().merged_with(metadata.config)
            grants = _resolve_tooling(config).grants
            sandbox = UserSandbox(report.identity, self._system_ops, shared_tool_grants=grants)
            sandbox.repair()
        return reports

    def cleanup_stale(self, dry_run: bool = False) -> list[StaleReport]:
        candidates = [r for r in self._reports() if not r.recoverable]
        if dry_run:
            return candidates
        for report in candidates:
            metadata = self._registry.get(report.identity.id)
            if metadata is not None:
                config = self._registry.global_config().merged_with(metadata.config)
                grants = _resolve_tooling(config).grants
                sandbox = UserSandbox(report.identity, self._system_ops, shared_tool_grants=grants)
            else:
                sandbox = UserSandbox(report.identity, self._system_ops)
            sandbox.destroy()
            self._registry.delete(report.identity.id)
        return candidates
