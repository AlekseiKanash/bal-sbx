"""`bal-sbx sandbox` — sandbox lifecycle subcommands.

`run` dispatches on `args.subcommand` to a `cmd_*` function.
"""

from __future__ import annotations

from argparse import Namespace
from collections.abc import Callable
from dataclasses import replace

from bal_sbx.api import SandboxManager
from bal_sbx.cli.output import emit, emit_sandbox_table, emit_stale_reports
from bal_sbx.cli.workspace import resolve_workspace
from bal_sbx.core.config import SandboxConfig

ManagerFactory = Callable[[], SandboxManager]


def cmd_list(args: Namespace, manager_factory: ManagerFactory) -> int:
    del args
    manager = manager_factory()
    rows = manager.list()
    if not rows:
        emit("No sandboxes registered.")
        return 0
    emit_sandbox_table(rows)
    return 0


def cmd_create(args: Namespace, manager_factory: ManagerFactory) -> int:
    workspace = resolve_workspace(args.workspace)
    manager = manager_factory()
    sandbox = manager.get_or_create(workspace, kind=args.type)
    identity = sandbox.identity
    emit(
        f"created sandbox {identity.id} "
        f"(user={identity.user}, home={identity.home})"
    )
    return 0


def cmd_repair(args: Namespace, manager_factory: ManagerFactory) -> int:
    manager = manager_factory()
    reports = manager.repair_all(dry_run=args.dry_run)
    if not reports:
        emit("All sandboxes healthy.")
        return 0
    action = "would repair" if args.dry_run else "repaired"
    emit_stale_reports(reports, action=action)
    return 0


def cmd_cleanup(args: Namespace, manager_factory: ManagerFactory) -> int:
    manager = manager_factory()
    candidates = manager.cleanup_stale(dry_run=True)
    if not candidates:
        emit("No stale sandboxes to clean up.")
        return 0

    action = "would remove" if args.dry_run else "to remove"
    emit_stale_reports(candidates, action=action)

    if args.dry_run:
        return 0

    if not args.yes:
        answer = input(
            f"Destroy {len(candidates)} sandbox(es)? [y/N]: "
        ).strip().lower()
        if answer != "y":
            emit("Aborted.")
            return 0

    manager.cleanup_stale(dry_run=False)
    emit(f"Removed {len(candidates)} sandbox(es).")
    return 0


def _global_config(manager: SandboxManager) -> SandboxConfig:
    return manager._registry.global_config()


def _set_global_env(manager: SandboxManager, key: str, value: str) -> None:
    cfg = _global_config(manager)
    new_env = {**cfg.env, key: value}
    manager._registry.set_global_config(replace(cfg, env=new_env))


def _unset_global_env(manager: SandboxManager, key: str) -> None:
    cfg = _global_config(manager)
    if key not in cfg.env:
        return
    new_env = {k: v for k, v in cfg.env.items() if k != key}
    manager._registry.set_global_config(replace(cfg, env=new_env))


def cmd_env(args: Namespace, manager_factory: ManagerFactory) -> int:
    manager = manager_factory()

    if args.is_global:
        cfg = _global_config(manager)
        env = dict(cfg.env)

        if args.unset is not None:
            _unset_global_env(manager, args.unset)
            return 0

        if args.key is None:
            for key in sorted(env):
                emit(f"{key}={env[key]}")
            return 0

        if args.value is None:
            if args.key not in env:
                return 1
            emit(env[args.key])
            return 0

        _set_global_env(manager, args.key, args.value)
        return 0

    workspace = resolve_workspace(args.workspace)

    if args.unset is not None:
        def _drop(cfg: SandboxConfig) -> SandboxConfig:
            if args.unset not in cfg.env:
                return cfg
            new_env = {k: v for k, v in cfg.env.items() if k != args.unset}
            return replace(cfg, env=new_env)

        manager.update_config(workspace, _drop)
        return 0

    if args.key is None:
        identity = manager.resolve(workspace)
        meta = manager._registry.get(identity.id)
        env = dict(meta.config.env) if meta is not None else {}
        for key in sorted(env):
            emit(f"{key}={env[key]}")
        return 0

    if args.value is None:
        identity = manager.resolve(workspace)
        meta = manager._registry.get(identity.id)
        env = dict(meta.config.env) if meta is not None else {}
        if args.key not in env:
            return 1
        emit(env[args.key])
        return 0

    def _set(cfg: SandboxConfig) -> SandboxConfig:
        new_env = {**cfg.env, args.key: args.value}
        return replace(cfg, env=new_env)

    manager.update_config(workspace, _set)
    return 0


_HANDLERS: dict[str, Callable[[Namespace, ManagerFactory], int]] = {
    "list": cmd_list,
    "create": cmd_create,
    "repair": cmd_repair,
    "cleanup": cmd_cleanup,
    "env": cmd_env,
}


def run(args: Namespace, manager_factory: ManagerFactory) -> int:
    return _HANDLERS[args.subcommand](args, manager_factory)
