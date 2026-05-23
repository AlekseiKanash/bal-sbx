"""MacosAclManager — HFS+/APFS ACLs via chmod +a.

The rights string is pinned (see _RIGHTS) because the macOS chmod ACL DSL has
no canonical "rwx" shorthand and silently accepts misspelled rights — drift
would be invisible without an exact test assertion. The grammar is documented
in chmod(1).

Recursion is performed with stdlib `os.walk` (one chmod call per node) rather
than a `find` pipeline so the broker sees one privileged invocation per node
and tests can assert on the exact argv.
"""

from __future__ import annotations

import os
import subprocess
import sys

from bal_sbx.system.acl.base import AclManager
from bal_sbx.system.privilege import PrivilegeBroker

_RIGHTS = (
    "read,write,execute,delete,append,"
    "readattr,writeattr,readextattr,writeextattr,"
    "readsecurity,writesecurity,chown,"
    "list,search,add_file,add_subdirectory,delete_child"
)


def _grant_spec(username: str) -> str:
    return f"{username} allow {_RIGHTS}"


def _revoke_spec(username: str) -> str:
    return f"{username} allow {_RIGHTS}"


def _walk_paths(path: str) -> list[str]:
    if not os.path.isdir(path):
        return [path]
    nodes = [path]
    for root, dirs, files in os.walk(path):
        for name in dirs:
            nodes.append(os.path.join(root, name))
        for name in files:
            nodes.append(os.path.join(root, name))
    return nodes


class MacosAclManager(AclManager):
    def __init__(self, privilege: PrivilegeBroker) -> None:
        self._privilege = privilege

    def grant(self, path: str, username: str) -> None:
        spec = _grant_spec(username)
        for node in _walk_paths(path):
            self._privilege.run_privileged(["chmod", "+a", spec, node])

    def revoke(self, path: str, username: str) -> None:
        spec = _revoke_spec(username)
        for node in _walk_paths(path):
            self._privilege.run_privileged(["chmod", "-a", spec, node])

    def is_granted(self, path: str, username: str) -> bool:
        result = subprocess.run(
            ["ls", "-lde", path],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False
        needle = f" {username} allow"
        return any(needle in line for line in result.stdout.splitlines())

    def is_supported(self) -> bool:
        return sys.platform == "darwin"
