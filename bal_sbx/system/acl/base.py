"""ACL management capability — grant/revoke per-user filesystem access."""

from __future__ import annotations

from abc import ABC, abstractmethod

from bal_sbx.core.shared_tools import Permission


class AclManager(ABC):
    @abstractmethod
    def grant(
        self,
        path: str,
        username: str,
        permissions: frozenset[Permission] | None = None,
    ) -> None:
        """Grant `username` access to `path` via a platform ACL entry.

        When `permissions` is `None`, the full workspace rights set is
        granted (current default behavior). When a subset is supplied,
        only those rights are granted.
        """

    @abstractmethod
    def revoke(
        self,
        path: str,
        username: str,
        permissions: frozenset[Permission] | None = None,
    ) -> None:
        """Remove the ACL entry for `username` on `path`.

        `permissions` defaults to `None` (the full workspace rights set —
        symmetric with `grant`). Pass the same subset that was granted so
        the ACE is matched exactly on platforms that require exact rights.
        """

    @abstractmethod
    def is_granted(
        self,
        path: str,
        username: str,
        permissions: frozenset[Permission] | None = None,
    ) -> bool:
        """Return True if `username` currently holds an ACL entry on `path`.

        With `permissions=None`, any entry counts. With a subset, the
        entry's actual rights must be a superset of the requested subset.
        """

    @abstractmethod
    def is_supported(self) -> bool:
        """Return True if the host's filesystem supports the ACL operations above."""
