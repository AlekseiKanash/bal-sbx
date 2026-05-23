"""Sandbox ABC — the orchestration contract every backend implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import NoReturn

from bal_sbx.core.identity import SandboxIdentity
from bal_sbx.core.status import SandboxStatus


class Sandbox(ABC):
    identity: SandboxIdentity

    @abstractmethod
    def create(self) -> None: ...

    @abstractmethod
    def destroy(self) -> None: ...

    @abstractmethod
    def status(self) -> SandboxStatus: ...

    @abstractmethod
    def repair(self) -> list[SandboxStatus]: ...

    @abstractmethod
    def enter(self) -> NoReturn: ...
