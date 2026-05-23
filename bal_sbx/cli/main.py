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

ManagerFactory = Callable[[], SandboxManager]

COMMANDS: dict[str, Callable[[argparse.Namespace, ManagerFactory], int]] = {
    "capabilities": capabilities_cmd.run,
    "exec": exec_cmd.run,
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

    # Placeholder group; steps 10/11/12 attach the actual subcommands.
    sandbox_p = sub.add_parser("sandbox", help="sandbox lifecycle commands")
    sandbox_p.add_subparsers(dest="subcommand", required=True)

    return parser


def main(
    argv: Sequence[str] | None = None,
    manager_factory: ManagerFactory | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    factory: ManagerFactory = manager_factory or SandboxManager
    return COMMANDS[args.command](args, factory)
