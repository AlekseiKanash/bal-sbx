"""CLI dispatcher.

Two argv shapes:

1. **Run a command in the sandbox** — `bal-sbx [--workspace PATH] [--unsafe] <cmd>`.
   `<cmd>` is a single shell string (use quotes for multi-word commands).
   The sandbox for the resolved workspace is created on demand. The command
   is executed via `sh -c <cmd>` inside the sandbox.

2. **Management subcommand** — `bal-sbx sandbox …`, `bal-sbx tools …`, or
   `bal-sbx capabilities`. These dispatch through an argparse subparser tree.

Reserved subcommand names (`sandbox`, `tools`, `capabilities`) shadow the
run-in-sandbox path. To run a host script that happens to be named
`sandbox`, pass it as `./sandbox`.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from typing import NoReturn

from bal_sbx.api import SandboxManager, SandboxMode
from bal_sbx.cli.commands import capabilities as capabilities_cmd
from bal_sbx.cli.commands import sandbox as sandbox_cmd
from bal_sbx.cli.commands import tools as tools_cmd
from bal_sbx.cli.output import emit, emit_unsafe_banner
from bal_sbx.cli.workspace import resolve_workspace

ManagerFactory = Callable[[], SandboxManager]

RESERVED = ("sandbox", "tools", "capabilities")

COMMANDS: dict[str, Callable] = {
    "capabilities": capabilities_cmd.run,
    "sandbox": sandbox_cmd.run,
    "tools": tools_cmd.run,
}

_USAGE = "usage: bal-sbx [--workspace PATH] [--unsafe] <command>"

_HELP = """\
usage:
  bal-sbx [--workspace PATH] [--unsafe] <command>
  bal-sbx sandbox {list,create,repair,cleanup,env} [...]
  bal-sbx tools {list,add,remove,discover} [...]
  bal-sbx capabilities

Run <command> inside the sandbox for the current workspace (created on demand).
<command> is a single shell string -- quote multi-word commands.

Examples:
  bal-sbx sh                       # interactive shell as the sandbox user
  bal-sbx ./script.py              # run script via its shebang
  bal-sbx "python script.py arg"   # explicit interpreter, quoted as one arg
  bal-sbx --unsafe ./script.py     # bypass sandbox; banner printed to stderr
  bal-sbx --workspace /tmp/ws sh   # override workspace inference

Management:
  bal-sbx sandbox list
  bal-sbx sandbox create [--workspace PATH]
  bal-sbx sandbox repair [--workspace PATH] [--dry-run]
  bal-sbx sandbox cleanup [--dry-run] [--yes]
  bal-sbx sandbox env [--workspace PATH | --global] [KEY [VALUE]] [--unset KEY]
  bal-sbx tools list      [--workspace PATH | --sandbox ID | --global]
  bal-sbx tools add NAME  --path P [--path P ...] --perm read --perm execute
                          [--env KEY=VAL ...] [--workspace PATH | --sandbox ID | --global]
  bal-sbx tools remove NAME [--workspace PATH | --sandbox ID | --global]
  bal-sbx tools discover  [--apply [--workspace PATH | --sandbox ID | --global]]
  bal-sbx capabilities
"""


class _UsageError(Exception):
    pass


def _add_scope_flags(parser) -> None:
    parser.add_argument("--workspace", default=None, help="workspace root (default: cwd)")
    parser.add_argument("--sandbox", default=None, help="sandbox id (e.g. bal_abc123)")
    parser.add_argument(
        "--global",
        dest="is_global",
        action="store_true",
        help="operate on registry global config",
    )


def build_parser():
    """Argparse parser for management subcommands only.

    Run-in-sandbox dispatch bypasses argparse entirely so the user's command
    string never collides with argparse's own flag parsing.
    """
    import argparse

    parser = argparse.ArgumentParser(prog="bal-sbx", add_help=False)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("capabilities", help="print platform capability probe")

    sandbox_p = sub.add_parser("sandbox", help="sandbox lifecycle commands")
    sandbox_sub = sandbox_p.add_subparsers(dest="subcommand", required=True)

    sandbox_sub.add_parser("list", help="list registered sandboxes")

    create_p = sandbox_sub.add_parser(
        "create", help="create a sandbox for the workspace"
    )
    create_p.add_argument("--workspace", default=None, help="workspace root (default: inferred)")
    create_p.add_argument("--type", default="user", choices=["user"], help="backend kind")

    repair_p = sandbox_sub.add_parser("repair", help="repair stale sandboxes in place")
    repair_p.add_argument("--workspace", default=None)
    repair_p.add_argument("--dry-run", action="store_true")

    cleanup_p = sandbox_sub.add_parser("cleanup", help="remove unrecoverable sandbox entries")
    cleanup_p.add_argument("--dry-run", action="store_true")
    cleanup_p.add_argument("--yes", action="store_true")

    env_p = sandbox_sub.add_parser("env", help="get/set persistent env vars (workspace or global)")
    env_p.add_argument("--workspace", default=None)
    env_p.add_argument(
        "--global",
        dest="is_global",
        action="store_true",
        help="operate on registry global env (default: per-sandbox)",
    )
    env_p.add_argument("--unset", metavar="KEY", default=None)
    env_p.add_argument("key", nargs="?", default=None)
    env_p.add_argument("value", nargs="?", default=None)

    tools_p = sub.add_parser("tools", help="manage shared host tools")
    tools_sub = tools_p.add_subparsers(dest="subcommand", required=True)

    list_p = tools_sub.add_parser("list", help="list shared tools in a scope")
    _add_scope_flags(list_p)

    add_p = tools_sub.add_parser("add", help="add a shared tool to a scope")
    add_p.add_argument("name")
    add_p.add_argument("--path", dest="paths", action="append", required=True)
    add_p.add_argument(
        "--perm", dest="perms", action="append", required=True,
        choices=["read", "execute", "write", "env"],
    )
    add_p.add_argument(
        "--env", dest="envs", action="append", default=[], metavar="KEY=VAL",
    )
    _add_scope_flags(add_p)

    remove_p = tools_sub.add_parser("remove", help="remove a shared tool (revokes ACLs)")
    remove_p.add_argument("name")
    _add_scope_flags(remove_p)

    discover_p = tools_sub.add_parser(
        "discover", help="detect host-installed tools and optionally apply",
    )
    discover_p.add_argument(
        "--apply", action="store_true",
        help="write discovered tools into the chosen scope",
    )
    _add_scope_flags(discover_p)

    return parser


def _extract_globals(argv: list[str]) -> tuple[str | None, bool, list[str]]:
    """Pull `--workspace PATH` / `--workspace=PATH` / `--unsafe` off the front of argv.

    Stops at the first non-flag token or at `--` (which is consumed as a
    separator). Raises `_UsageError` for unknown `--`-prefixed tokens or a
    bare `--workspace` with no value.
    """
    workspace: str | None = None
    unsafe = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--":
            i += 1
            break
        if a == "--unsafe":
            unsafe = True
            i += 1
        elif a == "--workspace":
            if i + 1 >= len(argv):
                raise _UsageError("--workspace requires a value")
            workspace = argv[i + 1]
            i += 2
        elif a.startswith("--workspace="):
            workspace = a.split("=", 1)[1]
            i += 1
        elif a.startswith("--"):
            raise _UsageError(f"unknown flag: {a} (quote multi-word commands: bal-sbx \"<cmd>\")")
        else:
            break
    return workspace, unsafe, argv[i:]


def _print_help(stream=None) -> None:
    print(_HELP, file=stream or sys.stdout, end="")


def _usage_error(message: str | None = None) -> int:
    if message:
        emit(message, level="error")
    emit(_USAGE, level="error")
    return 2


def _run_in_sandbox(
    cmd_string: str,
    workspace: str | None,
    unsafe: bool,
    factory: ManagerFactory,
) -> NoReturn:
    workspace_path = resolve_workspace(workspace)
    manager = factory()
    if unsafe:
        emit_unsafe_banner()
        launcher = manager.unsafe(workspace_path)
    else:
        launcher = manager.launcher(workspace_path, mode=SandboxMode.SAFE)
    launcher.exec_replace(["sh", "-c", cmd_string])
    raise RuntimeError("exec_replace returned unexpectedly")


def main(
    argv: Sequence[str] | None = None,
    manager_factory: ManagerFactory | None = None,
) -> int:
    argv_list = list(sys.argv[1:] if argv is None else argv)
    factory: ManagerFactory = manager_factory or SandboxManager

    if not argv_list:
        _print_help(stream=sys.stderr)
        return 2
    if argv_list[0] in ("-h", "--help"):
        _print_help()
        return 0

    if argv_list[0] in RESERVED:
        parser = build_parser()
        args = parser.parse_args(argv_list)
        return COMMANDS[args.command](args, factory)

    try:
        workspace, unsafe, rest = _extract_globals(argv_list)
    except _UsageError as exc:
        return _usage_error(str(exc))

    if not rest:
        return _usage_error()
    if rest[0] in RESERVED:
        parser = build_parser()
        args = parser.parse_args(rest)
        return COMMANDS[args.command](args, factory)
    if len(rest) != 1:
        return _usage_error(
            "expected one positional <command>; "
            "quote multi-word commands: bal-sbx \"<cmd>\""
        )

    _run_in_sandbox(rest[0], workspace, unsafe, factory)
