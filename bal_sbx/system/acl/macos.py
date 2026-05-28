"""MacosAclManager — HFS+/APFS ACLs via chmod +a.

The full-rights string is pinned (see `_FULL_RIGHTS`) because the macOS chmod
ACL DSL has no canonical "rwx" shorthand and silently accepts misspelled
rights — drift would be invisible without an exact test assertion. The
grammar is documented in chmod(1).

When a permission subset is requested, `_rights_for` translates the subset
into the matching slice of the canonical right set, preserving canonical
order so the resulting string is deterministic.

Recursion is performed with stdlib `os.walk` (one chmod call per node)
rather than a `find` pipeline so the broker sees one privileged invocation
per node and tests can assert on the exact argv.
"""

from __future__ import annotations

import os
import subprocess
import sys

from bal_sbx.core.shared_tools import Permission
from bal_sbx.system.acl.base import AclManager
from bal_sbx.system.privilege import PrivilegeBroker

_FULL_RIGHTS = (
    "read,write,execute,delete,append,"
    "readattr,writeattr,readextattr,writeextattr,"
    "readsecurity,writesecurity,chown,"
    "list,search,add_file,add_subdirectory,delete_child"
)

# Canonical order of every right in the full set — used to keep subset
# strings deterministic (and matchable by tests).
_CANONICAL_ORDER: tuple[str, ...] = tuple(_FULL_RIGHTS.split(","))

_PERMISSION_RIGHTS: dict[Permission, frozenset[str]] = {
    Permission.READ: frozenset(
        {"read", "readattr", "readextattr", "readsecurity", "list", "search"}
    ),
    Permission.EXECUTE: frozenset({"execute", "search"}),
    Permission.WRITE: frozenset(
        {
            "write", "append", "delete",
            "writeattr", "writeextattr", "writesecurity",
            "chown", "add_file", "add_subdirectory", "delete_child",
        }
    ),
}


def _rights_for(permissions: frozenset[Permission] | None) -> str:
    if permissions is None:
        return _FULL_RIGHTS
    enabled: set[str] = set()
    for perm in permissions:
        enabled |= _PERMISSION_RIGHTS.get(perm, frozenset())
    if not enabled:
        # Defensive — should be unreachable thanks to SharedTool validation,
        # but guarantees we never issue a `chmod +a "user allow "` (empty
        # rights string is rejected by chmod).
        return _FULL_RIGHTS
    return ",".join(r for r in _CANONICAL_ORDER if r in enabled)


def _grant_spec(username: str, permissions: frozenset[Permission] | None = None) -> str:
    return f"{username} allow {_rights_for(permissions)}"


def _revoke_spec(username: str, permissions: frozenset[Permission] | None = None) -> str:
    return f"{username} allow {_rights_for(permissions)}"


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

    def grant(
        self,
        path: str,
        username: str,
        permissions: frozenset[Permission] | None = None,
    ) -> None:
        spec = _grant_spec(username, permissions)
        for node in _walk_paths(path):
            self._privilege.run_privileged(["chmod", "+a", spec, node])

    def revoke(
        self,
        path: str,
        username: str,
        permissions: frozenset[Permission] | None = None,
    ) -> None:
        spec = _revoke_spec(username, permissions)
        for node in _walk_paths(path):
            self._privilege.run_privileged(["chmod", "-a", spec, node])

    def is_granted(
        self,
        path: str,
        username: str,
        permissions: frozenset[Permission] | None = None,
    ) -> bool:
        result = subprocess.run(
            ["ls", "-lde", path],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False
        # `ls -lde` prints active user ACEs as `<N>: user:<name> allow <rights>`.
        # For deleted principals it falls back to the bare UUID, which we
        # treat as not-granted (the named user we asked about no longer maps).
        needle = f" user:{username} allow"
        for line in result.stdout.splitlines():
            idx = line.find(needle)
            if idx < 0:
                continue
            if permissions is None:
                return True
            rights_csv = line[idx + len(needle):].strip()
            actual = {r.strip() for r in rights_csv.split(",") if r.strip()}
            expected = {r for perm in permissions for r in _PERMISSION_RIGHTS.get(perm, frozenset())}
            if expected.issubset(actual):
                return True
        return False

    def is_supported(self) -> bool:
        return sys.platform == "darwin"
