"""ACL management capability — grant/revoke per-user filesystem access."""

from __future__ import annotations

from abc import ABC, abstractmethod


class AclManager(ABC):
    @abstractmethod
    def grant(self, path: str, username: str) -> None:
        """Grant `username` access to `path` via a platform ACL entry."""

    @abstractmethod
    def revoke(self, path: str, username: str) -> None:
        """Remove the ACL entry for `username` on `path`."""

    @abstractmethod
    def is_granted(self, path: str, username: str) -> bool:
        """Return True if `username` currently holds an ACL entry on `path`."""

    @abstractmethod
    def is_supported(self) -> bool:
        """Return True if the host's filesystem supports the ACL operations above."""
