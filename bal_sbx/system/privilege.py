"""Privilege escalation broker — runs commands as root, or reports unavailable."""

from __future__ import annotations

import shutil
import subprocess
from abc import ABC, abstractmethod


class PrivilegeBroker(ABC):
    @abstractmethod
    def run_privileged(self, argv: list[str]) -> subprocess.CompletedProcess:
        """Run `argv` with elevated privileges and return the completed process."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if privilege escalation is usable on this host without prompts."""


class NullPrivilegeBroker(PrivilegeBroker):
    """No-op broker used by fakes — runs nothing, returns success."""

    def run_privileged(self, argv: list[str]) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    def is_available(self) -> bool:
        return False


class SudoBroker(PrivilegeBroker):
    """Caches the sudo timestamp once, then runs privileged commands without re-prompting.

    The cache is established lazily on the first `run_privileged` call via
    `sudo -v`. Subsequent invocations use `sudo -n` so a stale timestamp
    surfaces as a non-zero exit (which triggers exactly one re-validation
    before propagating the error).
    """

    def __init__(self) -> None:
        self._validated = False

    def _validate(self) -> None:
        subprocess.run(["sudo", "-v"], check=True)
        self._validated = True

    def run_privileged(self, argv: list[str]) -> subprocess.CompletedProcess:
        if not self._validated:
            self._validate()
        cmd = ["sudo", "-n", *argv]
        try:
            return subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError:
            self._validate()
            return subprocess.run(cmd, check=True, capture_output=True, text=True)

    def is_available(self) -> bool:
        if shutil.which("sudo") is None:
            return False
        probe = subprocess.run(
            ["sudo", "-n", "true"], check=False, capture_output=True, text=True
        )
        return probe.returncode == 0


class SudoPerOpBroker(PrivilegeBroker):
    """Invokes sudo on every call. Suitable when settings.privilege.mode = 'per_operation'."""

    def run_privileged(self, argv: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(["sudo", *argv], check=True, capture_output=True, text=True)

    def is_available(self) -> bool:
        return shutil.which("sudo") is not None
