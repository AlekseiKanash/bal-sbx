"""`bal-sbx sandbox` — sandbox lifecycle subcommands.

`run` dispatches on `args.subcommand` to a `cmd_*` function.
"""

from __future__ import annotations

from argparse import Namespace
from collections.abc import Callable

from bal_sbx.api import SandboxManager
from bal_sbx.cli.output import emit, emit_sandbox_table, emit_stale_reports
from bal_sbx.cli.workspace import resolve_workspace
from bal_sbx.config.workspace import WorkspaceConfig

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


def cmd_env(args: Namespace, manager_factory: ManagerFactory) -> int:
    workspace = resolve_workspace(args.workspace)
    manager = manager_factory()
    config = WorkspaceConfig(workspace, manager._path_layout)

    if args.unset is not None:
        config.unset_env(args.unset)
        return 0

    if args.key is None:
        env = config.env()
        for key in sorted(env):
            emit(f"{key}={env[key]}")
        return 0

    if args.value is None:
        env = config.env()
        if args.key not in env:
            return 1
        emit(env[args.key])
        return 0

    config.set_env(args.key, args.value)
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
