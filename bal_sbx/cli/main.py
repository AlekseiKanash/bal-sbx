"""CLI orchestrator.

`main` is a pure dispatcher per the `orchestrators route — they don't reason`
rule: parse argv, look the handler up in `COMMANDS`, return its exit code.
All business logic lives in `bal_sbx.cli.commands.*`.

`manager_factory` exists for tests, which inject a factory that returns a
`SandboxManager` constructed with `FakeSystemOps`. Production callers omit it.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence

from bal_sbx.api import SandboxManager
from bal_sbx.cli.commands import capabilities as capabilities_cmd
from bal_sbx.cli.commands import exec_cmd
from bal_sbx.cli.commands import sandbox as sandbox_cmd

ManagerFactory = Callable[[], SandboxManager]

COMMANDS: dict[str, Callable[[argparse.Namespace, ManagerFactory], int]] = {
    "capabilities": capabilities_cmd.run,
    "exec": exec_cmd.run,
    "sandbox": sandbox_cmd.run,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bal-sbx")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("capabilities", help="print platform capability probe")

    exec_p = sub.add_parser(
        "exec",
        help="run a command inside the sandbox (default) or directly (--unsafe)",
    )
    exec_p.add_argument("--workspace", default=None, help="workspace root (default: inferred)")
    exec_p.add_argument("--unsafe", action="store_true", help="bypass sandbox; run as host user")
    exec_p.add_argument("cmd", nargs=argparse.REMAINDER, help="command and args after --")

    sandbox_p = sub.add_parser("sandbox", help="sandbox lifecycle commands")
    sandbox_sub = sandbox_p.add_subparsers(dest="subcommand", required=True)

    sandbox_sub.add_parser("list", help="list registered sandboxes")

    create_p = sandbox_sub.add_parser(
        "create", help="create a sandbox for the workspace"
    )
    create_p.add_argument("--workspace", default=None, help="workspace root (default: inferred)")
    create_p.add_argument(
        "--type", default="user", choices=["user"], help="backend kind"
    )

    cd_p = sandbox_sub.add_parser("cd", help="enter the sandbox via a login shell")
    cd_p.add_argument("--workspace", default=None, help="workspace root (default: inferred)")

    repair_p = sandbox_sub.add_parser(
        "repair", help="repair stale sandboxes in place"
    )
    repair_p.add_argument(
        "--workspace", default=None, help="workspace root (default: inferred)"
    )
    repair_p.add_argument(
        "--dry-run", action="store_true", help="show what would be repaired without acting"
    )

    cleanup_p = sandbox_sub.add_parser(
        "cleanup", help="remove unrecoverable sandbox entries"
    )
    cleanup_p.add_argument(
        "--dry-run", action="store_true", help="show what would be removed without acting"
    )
    cleanup_p.add_argument(
        "--yes", action="store_true", help="skip confirmation prompt"
    )

    return parser


def main(
    argv: Sequence[str] | None = None,
    manager_factory: ManagerFactory | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    factory: ManagerFactory = manager_factory or SandboxManager
    return COMMANDS[args.command](args, factory)
