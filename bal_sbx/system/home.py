"""HomeLayout — sandbox HOME directory plus the `.bal/workspace` symlink."""

from __future__ import annotations

import os
import shutil
from abc import ABC, abstractmethod

from bal_sbx.system.privilege import PrivilegeBroker


class HomeLayout(ABC):
    @abstractmethod
    def create(self, home: str, username: str) -> None:
        """Create the sandbox HOME at `home`, owned by `username`."""

    @abstractmethod
    def destroy(self, home: str) -> None:
        """Recursively remove the sandbox HOME at `home`."""

    @abstractmethod
    def exists(self, home: str) -> bool:
        """Return True if the sandbox HOME at `home` currently exists."""

    @abstractmethod
    def link_workspace(self, home: str, workspace: str) -> None:
        """Create or replace `<home>/.bal/workspace` so it points at `workspace`."""

    @abstractmethod
    def workspace_link_target(self, home: str) -> str | None:
        """Return the current target of `<home>/.bal/workspace`, or None if absent."""


_WORKSPACE_PARENT = ".bal"
_WORKSPACE_LINK = "workspace"


def _workspace_link_path(home: str) -> str:
    return os.path.join(home, _WORKSPACE_PARENT, _WORKSPACE_LINK)


class RealHomeLayout(HomeLayout):
    """Filesystem-backed home layout that uses stdlib only.

    Directory creation and symlink management are unprivileged; ownership
    transfer to the sandbox user is privileged and routed through
    `PrivilegeBroker` (the only escalation this class performs).
    """

    def __init__(self, privilege: PrivilegeBroker) -> None:
        self._privilege = privilege

    def create(self, home: str, username: str) -> None:
        os.makedirs(home, exist_ok=True)
        self._privilege.run_privileged(["chown", "-R", username, home])

    def destroy(self, home: str) -> None:
        if os.path.isdir(home):
            shutil.rmtree(home)

    def exists(self, home: str) -> bool:
        return os.path.isdir(home)

    def link_workspace(self, home: str, workspace: str) -> None:
        link = _workspace_link_path(home)
        os.makedirs(os.path.dirname(link), exist_ok=True)
        if os.path.islink(link) or os.path.exists(link):
            os.unlink(link)
        os.symlink(workspace, link)

    def workspace_link_target(self, home: str) -> str | None:
        link = _workspace_link_path(home)
        if not os.path.islink(link):
            return None
        return os.readlink(link)
