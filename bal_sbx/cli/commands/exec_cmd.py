"""`bal-sbx exec` — run a command sandboxed (default) or directly (`--unsafe`).

Filename avoids shadowing the builtin `exec`.
"""

from __future__ import annotations

from argparse import Namespace
from collections.abc import Callable, Sequence
from typing import NoReturn

from bal_sbx.api import SandboxManager, SandboxMode
from bal_sbx.cli.output import emit, emit_unsafe_banner
from bal_sbx.cli.workspace import resolve_workspace
from bal_sbx.exec.launcher import AgentLauncher


def _strip_separator(cmd: Sequence[str]) -> list[str]:
    cmd_list = list(cmd)
    if cmd_list and cmd_list[0] == "--":
        cmd_list = cmd_list[1:]
    return cmd_list


def _exec(launcher: AgentLauncher, cmd: Sequence[str]) -> NoReturn:
    launcher.exec_replace(cmd)
    raise RuntimeError("exec_replace returned unexpectedly")


def run(args: Namespace, manager_factory: Callable[[], SandboxManager]) -> int:
    cmd = _strip_separator(args.cmd or [])
    if not cmd:
        emit(
            "usage: bal-sbx exec [--workspace PATH] [--unsafe] -- <cmd> [args...]",
            level="error",
        )
        return 2

    workspace = resolve_workspace(args.workspace)
    manager = manager_factory()

    if args.unsafe:
        emit_unsafe_banner()
        launcher = manager.unsafe(workspace)
    else:
        launcher = manager.launcher(workspace, mode=SandboxMode.SAFE)

    _exec(launcher, cmd)
