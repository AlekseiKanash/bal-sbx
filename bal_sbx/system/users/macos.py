"""MacosUserProvisioner — manages local users via dscl.

`dscl` is used (not `sysadminctl`) because it is reliable in non-GUI contexts
and is the documented modern interface for the Open Directory database.

For username `<user>` with home `<home>`, `create` issues this argv sequence,
each call routed through `PrivilegeBroker.run_privileged`:

    dscl . -create /Users/<user>
    dscl . -create /Users/<user> UserShell /bin/bash
    dscl . -create /Users/<user> RealName <user>
    dscl . -create /Users/<user> UniqueID <uid>
    dscl . -create /Users/<user> PrimaryGroupID 20
    dscl . -create /Users/<user> NFSHomeDirectory <home>

`<uid>` is derived deterministically from `<user>` via `_uid_for(username)` so
the argv is reproducible in tests and stable across invocations. The hash maps
into 600-999, comfortably above macOS's "_" service accounts (<500) and the
501+ range used for interactive humans. Collisions in this 400-slot space are
acceptable for sandbox users since each workspace's identity is itself a hash.

`delete` issues:

    dscl . -delete /Users/<user>

Existence is probed via the stdlib `pwd` database (unprivileged).
"""

from __future__ import annotations

import hashlib
import pwd

from bal_sbx.system.privilege import PrivilegeBroker
from bal_sbx.system.users.base import UserProvisioner

_UID_MIN = 600
_UID_RANGE = 400


def _uid_for(username: str) -> int:
    digest = hashlib.blake2s(username.encode(), digest_size=2).digest()
    return _UID_MIN + int.from_bytes(digest, "big") % _UID_RANGE


class MacosUserProvisioner(UserProvisioner):
    def __init__(self, privilege: PrivilegeBroker) -> None:
        self._privilege = privilege

    def exists(self, username: str) -> bool:
        try:
            pwd.getpwnam(username)
        except KeyError:
            return False
        return True

    def create(self, username: str, home: str) -> None:
        record = f"/Users/{username}"
        uid = str(_uid_for(username))
        steps = [
            ["dscl", ".", "-create", record],
            ["dscl", ".", "-create", record, "UserShell", "/bin/bash"],
            ["dscl", ".", "-create", record, "RealName", username],
            ["dscl", ".", "-create", record, "UniqueID", uid],
            ["dscl", ".", "-create", record, "PrimaryGroupID", "20"],
            ["dscl", ".", "-create", record, "NFSHomeDirectory", home],
        ]
        for argv in steps:
            self._privilege.run_privileged(argv)

    def delete(self, username: str) -> None:
        self._privilege.run_privileged(["dscl", ".", "-delete", f"/Users/{username}"])
