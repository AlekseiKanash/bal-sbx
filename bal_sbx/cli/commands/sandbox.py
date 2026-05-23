"""`bal-sbx sandbox` — sandbox lifecycle subcommands.

`run` dispatches on `args.subcommand` to a `cmd_*` function. Stubs for
`repair`, `cleanup`, and `env` raise NotImplementedError until steps 11
and 12 fill them in (and register their argparse parsers in `main.py`).
"""

from __future__ import annotations

from argparse import Namespace
from collections.abc import Callable
from typing import NoReturn

from bal_sbx.api import SandboxManager
from bal_sbx.cli.output import emit, emit_sandbox_table
from bal_sbx.cli.workspace import resolve_workspace

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


def cmd_cd(args: Namespace, manager_factory: ManagerFactory) -> int:
    workspace = resolve_workspace(args.workspace)
    manager = manager_factory()
    identity = manager.resolve(workspace)
    if manager._registry.get(identity.id) is None:
        emit(
            "SandboxNotFound: run 'bal-sbx sandbox create' first",
            level="error",
        )
        return 2
    sandbox = manager.get_or_create(workspace)
    _enter(sandbox)


def _enter(sandbox) -> NoReturn:
    sandbox.enter()
    raise RuntimeError("sandbox.enter returned unexpectedly")


def cmd_repair(args: Namespace, manager_factory: ManagerFactory) -> int:
    del args, manager_factory
    raise NotImplementedError("cmd_repair lands in step 11")


def cmd_cleanup(args: Namespace, manager_factory: ManagerFactory) -> int:
    del args, manager_factory
    raise NotImplementedError("cmd_cleanup lands in step 11")


def cmd_env(args: Namespace, manager_factory: ManagerFactory) -> int:
    del args, manager_factory
    raise NotImplementedError("cmd_env lands in step 12")


_HANDLERS: dict[str, Callable[[Namespace, ManagerFactory], int]] = {
    "list": cmd_list,
    "create": cmd_create,
    "cd": cmd_cd,
    "repair": cmd_repair,
    "cleanup": cmd_cleanup,
    "env": cmd_env,
}


def run(args: Namespace, manager_factory: ManagerFactory) -> int:
    return _HANDLERS[args.subcommand](args, manager_factory)
