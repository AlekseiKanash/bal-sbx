"""LinuxUserProvisioner — manages local users via useradd / userdel.

Privileged invocations are routed through a PrivilegeBroker. The unprivileged
existence probe uses the stdlib `pwd` database directly.
"""

from __future__ import annotations

import pwd

from bal_sbx.system.privilege import PrivilegeBroker
from bal_sbx.system.users.base import UserProvisioner


class LinuxUserProvisioner(UserProvisioner):
    def __init__(self, privilege: PrivilegeBroker) -> None:
        self._privilege = privilege

    def exists(self, username: str) -> bool:
        try:
            pwd.getpwnam(username)
        except KeyError:
            return False
        return True

    def create(self, username: str, home: str) -> None:
        self._privilege.run_privileged(
            ["useradd", "-m", "-d", home, "-s", "/bin/bash", username]
        )

    def delete(self, username: str) -> None:
        self._privilege.run_privileged(["userdel", "-r", username])
