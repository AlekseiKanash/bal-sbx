"""UserSandbox — composes SystemOps providers into a create/status/repair/destroy lifecycle."""

from __future__ import annotations

import os
import shutil
from typing import NoReturn

from bal_sbx.backends.base import Sandbox
from bal_sbx.core.errors import SandboxBroken
from bal_sbx.core.identity import SandboxIdentity
from bal_sbx.core.status import SandboxStatus
from bal_sbx.system.ops import SystemOps


class UserSandbox(Sandbox):
    def __init__(self, identity: SandboxIdentity, system_ops: SystemOps) -> None:
        self.identity = identity
        self._ops = system_ops

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

    def destroy(self) -> None:
        identity = self.identity
        ops = self._ops
        failures: list[str] = []

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
        if not ops.acl.is_granted(identity.workspace, identity.user):
            ops.acl.grant(identity.workspace, identity.user)
            fixed.append(SandboxStatus.DANGLING_ACL)
        return fixed

    def enter(self) -> NoReturn:
        shell = "bash" if shutil.which("bash") else "/bin/sh"
        os.execvp("sudo", ["sudo", "-u", self.identity.user, "-H", shell, "-l"])
        raise RuntimeError("os.execvp returned unexpectedly")
