"""Output emission helpers.

This is the only module in `cli/` that writes to stdout/stderr — keeping
prints isolated here lets command modules stay pure (and easy to test).
"""

from __future__ import annotations

import sys

from bal_sbx.api import Capabilities
from bal_sbx.core.identity import SandboxIdentity
from bal_sbx.core.metadata import SandboxMetadata
from bal_sbx.core.staleness import StaleReport
from bal_sbx.core.status import SandboxStatus


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


def emit_sandbox_table(
    rows: list[tuple[SandboxIdentity, SandboxMetadata, SandboxStatus]],
) -> None:
    headers = ("ID", "WORKSPACE", "STATUS", "LAST USED")
    cells = [
        (identity.id, meta.workspace, status.value, meta.last_used_at)
        for identity, meta, status in rows
    ]
    widths = [
        max(len(headers[i]), max((len(row[i]) for row in cells), default=0))
        for i in range(len(headers))
    ]
    print(" ".join(headers[i].ljust(widths[i]) for i in range(len(headers))).rstrip())
    for row in cells:
        print(" ".join(row[i].ljust(widths[i]) for i in range(len(headers))).rstrip())


def emit_stale_reports(reports: list[StaleReport], *, action: str) -> None:
    for report in reports:
        statuses = ",".join(s.value for s in report.statuses) or "ok"
        print(f"{report.identity.id} {action}: {statuses}")
