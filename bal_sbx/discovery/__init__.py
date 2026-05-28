"""Tool discovery — detect host-installed tools so the CLI can suggest entries."""

from bal_sbx.discovery.tools import (
    DEFAULT_DETECTORS,
    BrewDetector,
    CargoDetector,
    Detector,
    GoDetector,
    NodeDetector,
    PythonDetector,
    discover_tools,
)

__all__ = [
    "DEFAULT_DETECTORS",
    "BrewDetector",
    "CargoDetector",
    "Detector",
    "GoDetector",
    "NodeDetector",
    "PythonDetector",
    "discover_tools",
]
