"""Host-installed tool detectors.

Each detector inspects the host (via `shutil.which` and `os.path.exists`)
and returns a `SharedTool` description if its tool is installed, or `None`.
Detectors carry their own platform check inside `detect()` — A1: branching
at the edges, not centralized.

Defaults never include `WRITE` — discovered tools should be safely shareable
(read+execute). Users who want a writable tool config can compose one
manually via `bal-sbx tools add`.
"""

from __future__ import annotations

import os
import shutil
from typing import Protocol

from bal_sbx.core.shared_tools import Permission, SharedTool


class Detector(Protocol):
    name: str

    def detect(self) -> SharedTool | None: ...


_READ_EXEC: frozenset[Permission] = frozenset({Permission.READ, Permission.EXECUTE})
_READ_EXEC_ENV: frozenset[Permission] = frozenset(
    {Permission.READ, Permission.EXECUTE, Permission.ENV}
)


class BrewDetector:
    name = "brew"

    _CANDIDATE_PREFIXES = ("/opt/homebrew", "/usr/local")

    def detect(self) -> SharedTool | None:
        for prefix in self._CANDIDATE_PREFIXES:
            binary = os.path.join(prefix, "bin", "brew")
            if not os.path.isfile(binary):
                continue
            paths = [os.path.join(prefix, "bin")]
            for sibling in ("Cellar", "opt"):
                candidate = os.path.join(prefix, sibling)
                if os.path.isdir(candidate):
                    paths.append(candidate)
            return SharedTool(
                name=self.name,
                paths=tuple(paths),
                permissions=_READ_EXEC_ENV,
                env={"HOMEBREW_PREFIX": prefix},
            )
        return None


class NodeDetector:
    name = "node"

    def detect(self) -> SharedTool | None:
        binary = shutil.which("node")
        if not binary:
            return None
        return SharedTool(
            name=self.name,
            paths=(binary,),
            permissions=_READ_EXEC,
        )


class PythonDetector:
    """Detects a specific Python minor version (e.g. ``3.11``)."""

    def __init__(self, version: str) -> None:
        self.version = version
        self.name = f"python{version.replace('.', '')}"  # python311

    def detect(self) -> SharedTool | None:
        binary = shutil.which(f"python{self.version}")
        if not binary:
            return None
        return SharedTool(
            name=self.name,
            paths=(binary,),
            permissions=_READ_EXEC,
        )


class CargoDetector:
    name = "cargo"

    def detect(self) -> SharedTool | None:
        candidate = os.path.expanduser("~/.cargo/bin")
        if not os.path.isdir(candidate):
            return None
        return SharedTool(
            name=self.name,
            paths=(candidate,),
            permissions=_READ_EXEC,
        )


class GoDetector:
    name = "go"

    def detect(self) -> SharedTool | None:
        binary = shutil.which("go")
        if not binary:
            return None
        return SharedTool(
            name=self.name,
            paths=(binary,),
            permissions=_READ_EXEC,
        )


DEFAULT_DETECTORS: tuple[Detector, ...] = (
    BrewDetector(),
    NodeDetector(),
    PythonDetector("3.11"),
    PythonDetector("3.12"),
    PythonDetector("3.13"),
    CargoDetector(),
    GoDetector(),
)


def discover_tools(
    detectors: tuple[Detector, ...] = DEFAULT_DETECTORS,
) -> dict[str, SharedTool]:
    found: dict[str, SharedTool] = {}
    for detector in detectors:
        result = detector.detect()
        if result is not None:
            found[result.name] = result
    return found
