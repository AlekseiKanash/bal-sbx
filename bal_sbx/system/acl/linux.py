"""LinuxAclManager — POSIX ACLs via setfacl / getfacl.

Write operations (`grant`, `revoke`) require privilege and are routed through
`PrivilegeBroker`. Read operations (`is_granted`) call `getfacl` directly since
it does not require elevation.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

from bal_sbx.system.acl.base import AclManager
from bal_sbx.system.privilege import PrivilegeBroker


class LinuxAclManager(AclManager):
    def __init__(self, privilege: PrivilegeBroker) -> None:
        self._privilege = privilege

    def grant(self, path: str, username: str) -> None:
        spec = f"u:{username}:rwx"
        self._privilege.run_privileged(["setfacl", "-Rm", spec, path])
        self._privilege.run_privileged(["setfacl", "-dRm", spec, path])

    def revoke(self, path: str, username: str) -> None:
        spec = f"u:{username}"
        self._privilege.run_privileged(["setfacl", "-Rx", spec, path])
        self._privilege.run_privileged(["setfacl", "-dRx", spec, path])

    def is_granted(self, path: str, username: str) -> bool:
        result = subprocess.run(
            ["getfacl", "-c", path],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False
        needle = f"user:{username}:"
        return any(line.startswith(needle) for line in result.stdout.splitlines())

    def is_supported(self) -> bool:
        return sys.platform == "linux" and shutil.which("setfacl") is not None
