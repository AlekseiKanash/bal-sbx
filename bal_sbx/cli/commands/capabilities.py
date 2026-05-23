"""`bal-sbx capabilities` — print platform capability probe."""

from __future__ import annotations

from argparse import Namespace
from collections.abc import Callable

from bal_sbx.api import SandboxManager
from bal_sbx.cli.output import emit_capabilities


def run(args: Namespace, manager_factory: Callable[[], SandboxManager]) -> int:
    del args  # capabilities takes no flags
    manager = manager_factory()
    emit_capabilities(manager.capabilities())
    return 0
