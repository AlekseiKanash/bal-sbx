"""In-memory fakes for the system layer.

Used by every later step's tests so sandbox lifecycle can be exercised without
touching real users, ACLs, filesystems, or sudo.
"""

from __future__ import annotations

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

    def grant(self, path: str, username: str) -> None:
        self.grants.setdefault(path, set()).add(username)

    def revoke(self, path: str, username: str) -> None:
        if path in self.grants:
            self.grants[path].discard(username)

    def is_granted(self, path: str, username: str) -> bool:
        return username in self.grants.get(path, set())

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
