"""UserSandbox — composes SystemOps providers into a create/status/repair/destroy lifecycle."""

from __future__ import annotations

import os
import shutil
from collections.abc import Sequence
from typing import NamedTuple, NoReturn

from bal_sbx.backends.base import Sandbox
from bal_sbx.core.errors import SandboxBroken
from bal_sbx.core.identity import SandboxIdentity
from bal_sbx.core.shared_tools import Permission
from bal_sbx.core.status import SandboxStatus
from bal_sbx.system.ops import SystemOps


class ToolGrant(NamedTuple):
    """One ACL-bearing entry derived from a `SharedTool` at lifecycle time.

    The list is resolved at the manager level (workspace ⊕ global config,
    paths-that-exist filter, permission subset) and passed in so the backend
    stays config-agnostic.
    """

    path: str
    permissions: frozenset[Permission]


class UserSandbox(Sandbox):
    def __init__(
        self,
        identity: SandboxIdentity,
        system_ops: SystemOps,
        shared_tool_grants: Sequence[ToolGrant] = (),
    ) -> None:
        self.identity = identity
        self._ops = system_ops
        self._shared_tool_grants = tuple(shared_tool_grants)

    def create(self) -> None:
        identity = self.identity
        ops = self._ops
        if not ops.users.exists(identity.user):
            ops.users.create(identity.user, identity.home)
        if not ops.home.exists(identity.home):
            ops.home.create(identity.home, identity.user)
        if ops.home.workspace_link_target(identity.home) != identity.workspace:
            ops.home.link_workspace(identity.home, identity.workspace)
        if not ops.acl.is_granted(identity.workspace, identity.user):
            ops.acl.grant(identity.workspace, identity.user)
        self._reconcile_shared_tools()

    def _reconcile_shared_tools(self) -> None:
        identity = self.identity
        for grant in self._shared_tool_grants:
            if not grant.permissions:
                continue
            if self._ops.acl.is_granted(grant.path, identity.user, grant.permissions):
                continue
            self._ops.acl.grant(grant.path, identity.user, grant.permissions)

    def destroy(self) -> None:
        identity = self.identity
        ops = self._ops
        failures: list[str] = []

        for grant in self._shared_tool_grants:
            if not grant.permissions:
                continue
            try:
                if ops.acl.is_granted(grant.path, identity.user, grant.permissions):
                    ops.acl.revoke(grant.path, identity.user, grant.permissions)
            except Exception as exc:
                failures.append(f"acl.revoke({grant.path}): {exc!r}")

        if ops.acl.is_granted(identity.workspace, identity.user):
            try:
                ops.acl.revoke(identity.workspace, identity.user)
            except Exception as exc:
                failures.append(f"acl.revoke: {exc!r}")

        if ops.home.exists(identity.home):
            try:
                ops.home.destroy(identity.home)
            except Exception as exc:
                failures.append(f"home.destroy: {exc!r}")

        if ops.users.exists(identity.user):
            try:
                ops.users.delete(identity.user)
            except Exception as exc:
                failures.append(f"users.delete: {exc!r}")

        if failures:
            raise SandboxBroken(
                f"destroy of {identity.id} failed: {'; '.join(failures)}"
            )

    def status(self) -> SandboxStatus:
        identity = self.identity
        ops = self._ops
        if not os.path.isdir(identity.workspace):
            return SandboxStatus.MISSING_WORKSPACE
        if not ops.users.exists(identity.user):
            return SandboxStatus.MISSING_USER
        if not ops.home.exists(identity.home):
            return SandboxStatus.MISSING_HOME
        if ops.home.workspace_link_target(identity.home) != identity.workspace:
            return SandboxStatus.BROKEN_SYMLINK
        if not ops.acl.is_granted(identity.workspace, identity.user):
            return SandboxStatus.DANGLING_ACL
        for grant in self._shared_tool_grants:
            if not grant.permissions:
                continue
            if not ops.acl.is_granted(grant.path, identity.user, grant.permissions):
                return SandboxStatus.DANGLING_ACL
        return SandboxStatus.OK

    def repair(self) -> list[SandboxStatus]:
        identity = self.identity
        ops = self._ops
        if not os.path.isdir(identity.workspace):
            raise SandboxBroken(
                f"cannot repair {identity.id}: workspace missing at {identity.workspace}"
            )
        fixed: list[SandboxStatus] = []
        if not ops.users.exists(identity.user):
            ops.users.create(identity.user, identity.home)
            fixed.append(SandboxStatus.MISSING_USER)
        if not ops.home.exists(identity.home):
            ops.home.create(identity.home, identity.user)
            fixed.append(SandboxStatus.MISSING_HOME)
        if ops.home.workspace_link_target(identity.home) != identity.workspace:
            ops.home.link_workspace(identity.home, identity.workspace)
            fixed.append(SandboxStatus.BROKEN_SYMLINK)
        acl_fixed = False
        if not ops.acl.is_granted(identity.workspace, identity.user):
            ops.acl.grant(identity.workspace, identity.user)
            acl_fixed = True
        for grant in self._shared_tool_grants:
            if not grant.permissions:
                continue
            if not ops.acl.is_granted(grant.path, identity.user, grant.permissions):
                ops.acl.grant(grant.path, identity.user, grant.permissions)
                acl_fixed = True
        if acl_fixed:
            fixed.append(SandboxStatus.DANGLING_ACL)
        return fixed

    def enter(self) -> NoReturn:
        shell = "bash" if shutil.which("bash") else "/bin/sh"
        os.execvp("sudo", ["sudo", "-u", self.identity.user, "-H", shell, "-l"])
        raise RuntimeError("os.execvp returned unexpectedly")
