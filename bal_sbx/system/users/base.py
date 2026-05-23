"""User provisioning capability — manage local OS users for sandboxes."""

from __future__ import annotations

from abc import ABC, abstractmethod


class UserProvisioner(ABC):
    @abstractmethod
    def exists(self, username: str) -> bool:
        """Return True if a local user named `username` exists on the host."""

    @abstractmethod
    def create(self, username: str, home: str) -> None:
        """Create a local user `username` whose home directory is `home`."""

    @abstractmethod
    def delete(self, username: str) -> None:
        """Remove the local user `username` from the host."""
