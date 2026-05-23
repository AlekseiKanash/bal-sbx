"""Output emission helpers.

This is the only module in `cli/` that writes to stdout/stderr — keeping
prints isolated here lets command modules stay pure (and easy to test).
"""

from __future__ import annotations

import sys

from bal_sbx.api import Capabilities


def emit(message: str, *, level: str = "info") -> None:
    stream = sys.stderr if level in ("warn", "error") else sys.stdout
    print(message, file=stream)


def emit_capabilities(caps: Capabilities) -> None:
    print(f"platform: {caps.platform}")
    print(f"can_sudo: {caps.can_sudo}")
    print(f"acl_supported: {caps.acl_supported}")
    if caps.unsupported_reason is not None:
        print(f"unsupported_reason: {caps.unsupported_reason}")


def emit_unsafe_banner() -> None:
    print("MODE: UNSAFE", file=sys.stderr)
