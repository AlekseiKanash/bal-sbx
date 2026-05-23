"""Stale-sandbox detection.

`detect_stale` is a **pure** function: it accepts a fully-formed
`(identity, metadata)` pair plus a `SystemOps` and returns a `StaleReport`
describing every detected issue. Unlike `Sandbox.status()`, which returns the
first failure, this runs all checks so callers (repair/cleanup) can act on
the complete picture.

ORPHAN_HOME and MISSING_USER are mutually exclusive: a missing user with an
intact HOME surfaces as ORPHAN_HOME; a missing user with no HOME surfaces as
MISSING_USER. This keeps each variant unambiguous in tests and reports.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

from bal_sbx.core.identity import SandboxIdentity
from bal_sbx.core.metadata import SandboxMetadata
from bal_sbx.core.status import SandboxStatus
from bal_sbx.system.ops import SystemOps


@dataclass(frozen=True)
class StaleReport:
    identity: SandboxIdentity
    metadata: SandboxMetadata
    statuses: list[SandboxStatus]
    recoverable: bool


_UNRECOVERABLE = frozenset(
    {SandboxStatus.MISSING_WORKSPACE, SandboxStatus.INVALID_METADATA}
)


def _metadata_is_valid(metadata: SandboxMetadata) -> bool:
    if not isinstance(metadata.workspace, str) or not metadata.workspace:
        return False
    for ts in (metadata.created_at, metadata.last_used_at):
        if not isinstance(ts, str) or not ts:
            return False
        try:
            datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return False
    return True


def detect_stale(
    identity: SandboxIdentity,
    metadata: SandboxMetadata,
    system_ops: SystemOps,
) -> StaleReport:
    statuses: list[SandboxStatus] = []

    if not _metadata_is_valid(metadata):
        statuses.append(SandboxStatus.INVALID_METADATA)

    workspace_present = os.path.isdir(identity.workspace)
    if not workspace_present:
        statuses.append(SandboxStatus.MISSING_WORKSPACE)

    user_present = system_ops.users.exists(identity.user)
    home_present = system_ops.home.exists(identity.home)

    if not user_present and home_present:
        statuses.append(SandboxStatus.ORPHAN_HOME)
    elif not user_present:
        statuses.append(SandboxStatus.MISSING_USER)

    if user_present and not home_present:
        statuses.append(SandboxStatus.MISSING_HOME)

    if home_present:
        target = system_ops.home.workspace_link_target(identity.home)
        if target != identity.workspace:
            statuses.append(SandboxStatus.BROKEN_SYMLINK)

    if workspace_present:
        if not system_ops.acl.is_granted(identity.workspace, identity.user):
            statuses.append(SandboxStatus.DANGLING_ACL)

    recoverable = not any(s in _UNRECOVERABLE for s in statuses)
    return StaleReport(
        identity=identity,
        metadata=metadata,
        statuses=statuses,
        recoverable=recoverable,
    )
