"""`bal-sbx tools` — manage shared host tools.

Subcommands:

    bal-sbx tools list      [--global | --sandbox ID | --workspace PATH]
    bal-sbx tools add NAME  --path P [--path P ...] --perm read --perm execute [--env KEY=VAL ...]
                            (--global | --sandbox ID | --workspace PATH)
    bal-sbx tools remove NAME (--global | --sandbox ID | --workspace PATH)
    bal-sbx tools discover  [--apply (--global | --sandbox ID | --workspace PATH)]

`tools remove` revokes ACLs on the affected paths *before* deleting the
config entry. When removing from `--global`, this loops over every sandbox
that doesn't override the tool by name in its per-sandbox config — those
sandboxes' ACLs are the ones the global definition is responsible for.
"""

from __future__ import annotations

import json
from argparse import Namespace
from collections.abc import Callable
from dataclasses import replace

from bal_sbx.api import SandboxManager
from bal_sbx.cli.output import emit
from bal_sbx.cli.workspace import resolve_workspace
from bal_sbx.core.errors import ConfigInvalid
from bal_sbx.core.identity import SandboxIdentity
from bal_sbx.core.shared_tools import Permission, SharedTool
from bal_sbx.discovery import discover_tools

ManagerFactory = Callable[[], SandboxManager]

# Canonical display order for permissions (matches the docs and the brew
# example in the design plan).
_PERMISSION_DISPLAY_ORDER: tuple[Permission, ...] = (
    Permission.READ,
    Permission.WRITE,
    Permission.EXECUTE,
    Permission.ENV,
)


def _resolve_scope(args: Namespace, manager: SandboxManager) -> tuple[str, str | None, str | None]:
    """Return (scope, workspace_path, sandbox_id).

    - ``global``: (``"global"``, None, None)
    - ``sandbox``: (``"sandbox"``, workspace_path, sandbox_id)

    Default when nothing is specified: the workspace inferred from cwd.
    """
    if args.is_global:
        return "global", None, None
    if args.sandbox is not None:
        meta = manager._registry.get(args.sandbox)
        if meta is None:
            raise ConfigInvalid(f"unknown sandbox: {args.sandbox}")
        return "sandbox", meta.workspace, args.sandbox
    workspace = resolve_workspace(args.workspace)
    identity = manager.resolve(workspace)
    return "sandbox", workspace, identity.id


def _tools_for_scope(
    manager: SandboxManager,
    scope: str,
    sandbox_id: str | None,
) -> dict[str, SharedTool]:
    if scope == "global":
        return dict(manager._registry.global_config().shared_tools)
    meta = manager._registry.get(sandbox_id) if sandbox_id else None
    if meta is None:
        return {}
    return dict(meta.config.shared_tools)


def _set_tools_for_scope(
    manager: SandboxManager,
    scope: str,
    workspace_path: str | None,
    tools: dict[str, SharedTool],
) -> None:
    if scope == "global":
        cfg = manager._registry.global_config()
        manager._registry.set_global_config(replace(cfg, shared_tools=tools))
        return
    assert workspace_path is not None
    manager.update_config(
        workspace_path,
        lambda cfg: replace(cfg, shared_tools=tools),
    )


def _format_permissions(perms: frozenset[Permission]) -> str:
    ordered = [p.value for p in _PERMISSION_DISPLAY_ORDER if p in perms]
    return ",".join(ordered)


def _emit_tools(tools: dict[str, SharedTool]) -> None:
    if not tools:
        emit("No shared tools configured.")
        return
    for name in sorted(tools):
        tool = tools[name]
        emit(f"{name}")
        for p in tool.paths:
            emit(f"  path: {p}")
        emit(f"  permissions: {_format_permissions(tool.permissions)}")
        if tool.env:
            for k, v in sorted(tool.env.items()):
                emit(f"  env: {k}={v}")


def _parse_env_pairs(values: list[str] | None) -> dict[str, str]:
    env: dict[str, str] = {}
    if not values:
        return env
    for raw in values:
        if "=" not in raw:
            raise ConfigInvalid(f"env must be KEY=VALUE, got {raw!r}")
        k, v = raw.split("=", 1)
        if not k:
            raise ConfigInvalid(f"env key cannot be empty: {raw!r}")
        env[k] = v
    return env


def cmd_list(args: Namespace, manager_factory: ManagerFactory) -> int:
    manager = manager_factory()
    scope, _workspace, sid = _resolve_scope(args, manager)
    _emit_tools(_tools_for_scope(manager, scope, sid))
    return 0


def cmd_add(args: Namespace, manager_factory: ManagerFactory) -> int:
    manager = manager_factory()
    scope, workspace_path, sid = _resolve_scope(args, manager)
    permissions = frozenset(Permission(p) for p in args.perms)
    env = _parse_env_pairs(args.envs)
    tool = SharedTool(
        name=args.name,
        paths=tuple(args.paths),
        permissions=permissions,
        env=env,
    )
    tools = _tools_for_scope(manager, scope, sid)
    tools[args.name] = tool
    _set_tools_for_scope(manager, scope, workspace_path, tools)
    return 0


def _affected_sandboxes_for_global_removal(
    manager: SandboxManager,
    tool_name: str,
) -> list[tuple[SandboxIdentity, SharedTool]]:
    """Find every sandbox whose effective config currently includes `tool_name`
    *from* the global section (i.e. without a per-sandbox override).
    """
    global_cfg = manager._registry.global_config()
    if tool_name not in global_cfg.shared_tools:
        return []
    global_tool = global_cfg.shared_tools[tool_name]
    affected: list[tuple[SandboxIdentity, SharedTool]] = []
    for sid, meta in manager._registry.list():
        del sid
        if tool_name in meta.config.shared_tools:
            # Overridden per-sandbox — global removal does not affect this one.
            continue
        identity = SandboxIdentity.from_workspace(meta.workspace, manager._path_layout)
        affected.append((identity, global_tool))
    return affected


def cmd_remove(args: Namespace, manager_factory: ManagerFactory) -> int:
    manager = manager_factory()
    scope, workspace_path, sid = _resolve_scope(args, manager)
    tools = _tools_for_scope(manager, scope, sid)
    if args.name not in tools:
        emit(f"tool {args.name!r} not found in {scope} config", level="error")
        return 1

    tool = tools[args.name]
    acl_perms = tool.acl_permissions

    if scope == "global":
        affected = _affected_sandboxes_for_global_removal(manager, args.name)
        for identity, gtool in affected:
            for p in gtool.paths:
                try:
                    if manager._system_ops.acl.is_granted(p, identity.user, gtool.acl_permissions):
                        manager._system_ops.acl.revoke(p, identity.user, gtool.acl_permissions)
                except Exception as exc:
                    emit(f"warn: revoke {p} for {identity.id}: {exc!r}", level="warn")
    else:
        assert sid is not None
        meta = manager._registry.get(sid)
        if meta is not None:
            identity = SandboxIdentity.from_workspace(meta.workspace, manager._path_layout)
            for p in tool.paths:
                try:
                    if manager._system_ops.acl.is_granted(p, identity.user, acl_perms):
                        manager._system_ops.acl.revoke(p, identity.user, acl_perms)
                except Exception as exc:
                    emit(f"warn: revoke {p} for {identity.id}: {exc!r}", level="warn")

    del tools[args.name]
    _set_tools_for_scope(manager, scope, workspace_path, tools)
    return 0


def cmd_discover(args: Namespace, manager_factory: ManagerFactory) -> int:
    manager = manager_factory()
    found = discover_tools()
    if args.apply:
        scope, workspace_path, sid = _resolve_scope(args, manager)
        tools = _tools_for_scope(manager, scope, sid)
        tools.update(found)
        _set_tools_for_scope(manager, scope, workspace_path, tools)
        if not found:
            emit("No host tools detected.")
        else:
            emit(f"Applied {len(found)} tool(s) to {scope} config: {', '.join(sorted(found))}")
        return 0

    if not found:
        emit("No host tools detected.")
        return 0
    snippet = {name: tool.to_dict() for name, tool in found.items()}
    emit(json.dumps({"shared_tools": snippet}, indent=2, sort_keys=True))
    return 0


_HANDLERS: dict[str, Callable[[Namespace, ManagerFactory], int]] = {
    "list": cmd_list,
    "add": cmd_add,
    "remove": cmd_remove,
    "discover": cmd_discover,
}


def run(args: Namespace, manager_factory: ManagerFactory) -> int:
    return _HANDLERS[args.subcommand](args, manager_factory)
