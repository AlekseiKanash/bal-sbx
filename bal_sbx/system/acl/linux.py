"""LinuxAclManager — POSIX ACLs via setfacl / getfacl.

Write operations (`grant`, `revoke`) require privilege and are routed through
`PrivilegeBroker`. Read operations (`is_granted`) call `getfacl` directly
since it does not require elevation.

When a permission subset is requested, the rwx string is composed from the
ACL-relevant permissions (`READ`/`WRITE`/`EXECUTE`); `Permission.ENV` is
informational and never appears on the ACL.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

from bal_sbx.core.shared_tools import Permission
from bal_sbx.system.acl.base import AclManager
from bal_sbx.system.privilege import PrivilegeBroker


_PERMISSION_LETTER: dict[Permission, str] = {
    Permission.READ: "r",
    Permission.WRITE: "w",
    Permission.EXECUTE: "x",
}


def _rights_for(permissions: frozenset[Permission] | None) -> str:
    if permissions is None:
        return "rwx"
    letters = "".join(
        letter
        for perm, letter in _PERMISSION_LETTER.items()
        if perm in permissions
    )
    # Defensive — SharedTool validation prevents an empty/ENV-only permission
    # set from being granted to ACL, but guarantee we never call setfacl
    # with an empty rights spec.
    return letters or "rwx"


class LinuxAclManager(AclManager):
    def __init__(self, privilege: PrivilegeBroker) -> None:
        self._privilege = privilege

    def grant(
        self,
        path: str,
        username: str,
        permissions: frozenset[Permission] | None = None,
    ) -> None:
        rights = _rights_for(permissions)
        spec = f"u:{username}:{rights}"
        self._privilege.run_privileged(["setfacl", "-Rm", spec, path])
        self._privilege.run_privileged(["setfacl", "-dRm", spec, path])

    def revoke(
        self,
        path: str,
        username: str,
        permissions: frozenset[Permission] | None = None,
    ) -> None:
        # setfacl -x ignores the rights portion — only the principal matters,
        # so the same call cleanly removes both full and subset grants.
        spec = f"u:{username}"
        self._privilege.run_privileged(["setfacl", "-Rx", spec, path])
        self._privilege.run_privileged(["setfacl", "-dRx", spec, path])

    def is_granted(
        self,
        path: str,
        username: str,
        permissions: frozenset[Permission] | None = None,
    ) -> bool:
        result = subprocess.run(
            ["getfacl", "-c", path],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False
        prefix = f"user:{username}:"
        for line in result.stdout.splitlines():
            if not line.startswith(prefix):
                continue
            if permissions is None:
                return True
            actual = line[len(prefix):].strip()
            expected_letters = {
                letter
                for perm, letter in _PERMISSION_LETTER.items()
                if perm in permissions
            }
            if expected_letters.issubset(set(actual)):
                return True
        return False

    def is_supported(self) -> bool:
        return sys.platform == "linux" and shutil.which("setfacl") is not None
