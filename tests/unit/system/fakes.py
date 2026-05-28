"""In-memory fakes for the system layer.

Used by every later step's tests so sandbox lifecycle can be exercised without
touching real users, ACLs, filesystems, or sudo.
"""

from __future__ import annotations

from bal_sbx.core.shared_tools import Permission
from bal_sbx.system.acl.base import AclManager
from bal_sbx.system.home import HomeLayout
from bal_sbx.system.ops import SystemOps
from bal_sbx.system.privilege import NullPrivilegeBroker
from bal_sbx.system.users.base import UserProvisioner


class FakeUserProvisioner(UserProvisioner):
    def __init__(self) -> None:
        self.users: set[str] = set()

    def exists(self, username: str) -> bool:
        return username in self.users

    def create(self, username: str, home: str) -> None:
        self.users.add(username)

    def delete(self, username: str) -> None:
        self.users.discard(username)


class FakeAclManager(AclManager):
    def __init__(self) -> None:
        self.grants: dict[str, set[str]] = {}
        # Permissions tracked separately so the legacy `.grants` shape
        # (dict[path, set[user]]) keeps working for existing test assertions.
        self.permissions: dict[tuple[str, str], frozenset[Permission] | None] = {}

    def grant(
        self,
        path: str,
        username: str,
        permissions: frozenset[Permission] | None = None,
    ) -> None:
        self.grants.setdefault(path, set()).add(username)
        self.permissions[(path, username)] = permissions

    def revoke(
        self,
        path: str,
        username: str,
        permissions: frozenset[Permission] | None = None,
    ) -> None:
        if path in self.grants:
            self.grants[path].discard(username)
        self.permissions.pop((path, username), None)

    def is_granted(
        self,
        path: str,
        username: str,
        permissions: frozenset[Permission] | None = None,
    ) -> bool:
        if username not in self.grants.get(path, set()):
            return False
        if permissions is None:
            return True
        stored = self.permissions.get((path, username))
        if stored is None:
            return True
        return permissions.issubset(stored)

    def is_supported(self) -> bool:
        return True


class FakeHomeLayout(HomeLayout):
    def __init__(self) -> None:
        self.homes: dict[str, str | None] = {}

    def create(self, home: str, username: str) -> None:
        self.homes.setdefault(home, None)

    def destroy(self, home: str) -> None:
        self.homes.pop(home, None)

    def exists(self, home: str) -> bool:
        return home in self.homes

    def link_workspace(self, home: str, workspace: str) -> None:
        self.homes[home] = workspace

    def workspace_link_target(self, home: str) -> str | None:
        return self.homes.get(home)


def FakeSystemOps() -> SystemOps:
    return SystemOps(
        users=FakeUserProvisioner(),
        acl=FakeAclManager(),
        home=FakeHomeLayout(),
        privilege=NullPrivilegeBroker(),
    )
