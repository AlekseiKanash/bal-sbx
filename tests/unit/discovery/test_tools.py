"""Tests for the discovery detectors."""

from __future__ import annotations

from bal_sbx.core.shared_tools import Permission
from bal_sbx.discovery.tools import (
    BrewDetector,
    CargoDetector,
    GoDetector,
    NodeDetector,
    PythonDetector,
    discover_tools,
)


def test_brew_detector_apple_silicon_prefix(monkeypatch):
    fs: set[str] = {
        "/opt/homebrew/bin/brew",
        "/opt/homebrew/bin",
        "/opt/homebrew/Cellar",
        "/opt/homebrew/opt",
    }
    monkeypatch.setattr("bal_sbx.discovery.tools.os.path.isfile", lambda p: p in fs)
    monkeypatch.setattr("bal_sbx.discovery.tools.os.path.isdir", lambda p: p in fs)
    tool = BrewDetector().detect()
    assert tool is not None
    assert tool.name == "brew"
    assert "/opt/homebrew/bin" in tool.paths
    assert "/opt/homebrew/Cellar" in tool.paths
    assert tool.env == {"HOMEBREW_PREFIX": "/opt/homebrew"}
    assert Permission.ENV in tool.permissions


def test_brew_detector_intel_prefix_fallback(monkeypatch):
    fs = {"/usr/local/bin/brew", "/usr/local/bin"}
    monkeypatch.setattr("bal_sbx.discovery.tools.os.path.isfile", lambda p: p in fs)
    monkeypatch.setattr("bal_sbx.discovery.tools.os.path.isdir", lambda p: p in fs)
    tool = BrewDetector().detect()
    assert tool is not None
    assert tool.env == {"HOMEBREW_PREFIX": "/usr/local"}
    assert "/usr/local/bin" in tool.paths


def test_brew_detector_returns_none_when_not_installed(monkeypatch):
    monkeypatch.setattr("bal_sbx.discovery.tools.os.path.isfile", lambda _: False)
    monkeypatch.setattr("bal_sbx.discovery.tools.os.path.isdir", lambda _: False)
    assert BrewDetector().detect() is None


def test_brew_detector_omits_missing_siblings(monkeypatch):
    fs = {"/opt/homebrew/bin/brew", "/opt/homebrew/bin"}  # No Cellar / opt
    monkeypatch.setattr("bal_sbx.discovery.tools.os.path.isfile", lambda p: p in fs)
    monkeypatch.setattr("bal_sbx.discovery.tools.os.path.isdir", lambda p: p in fs)
    tool = BrewDetector().detect()
    assert tool.paths == ("/opt/homebrew/bin",)


def test_node_detector_finds_via_which(monkeypatch):
    monkeypatch.setattr(
        "bal_sbx.discovery.tools.shutil.which",
        lambda name: "/opt/homebrew/bin/node" if name == "node" else None,
    )
    tool = NodeDetector().detect()
    assert tool is not None
    assert tool.name == "node"
    assert tool.paths == ("/opt/homebrew/bin/node",)


def test_node_detector_returns_none(monkeypatch):
    monkeypatch.setattr("bal_sbx.discovery.tools.shutil.which", lambda _: None)
    assert NodeDetector().detect() is None


def test_python_detector_name_format(monkeypatch):
    monkeypatch.setattr(
        "bal_sbx.discovery.tools.shutil.which",
        lambda name: "/usr/bin/python3.11" if name == "python3.11" else None,
    )
    tool = PythonDetector("3.11").detect()
    assert tool is not None
    assert tool.name == "python311"
    assert tool.paths == ("/usr/bin/python3.11",)


def test_python_detector_returns_none_when_missing(monkeypatch):
    monkeypatch.setattr("bal_sbx.discovery.tools.shutil.which", lambda _: None)
    assert PythonDetector("3.99").detect() is None


def test_cargo_detector_uses_home_dir(monkeypatch, tmp_path):
    cargo = tmp_path / ".cargo" / "bin"
    cargo.mkdir(parents=True)
    monkeypatch.setattr(
        "bal_sbx.discovery.tools.os.path.expanduser",
        lambda p: p.replace("~", str(tmp_path)),
    )
    tool = CargoDetector().detect()
    assert tool is not None
    assert tool.paths == (str(cargo),)


def test_cargo_detector_returns_none_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "bal_sbx.discovery.tools.os.path.expanduser",
        lambda p: p.replace("~", str(tmp_path)),
    )
    assert CargoDetector().detect() is None


def test_go_detector_finds_via_which(monkeypatch):
    monkeypatch.setattr(
        "bal_sbx.discovery.tools.shutil.which",
        lambda name: "/opt/go/bin/go" if name == "go" else None,
    )
    tool = GoDetector().detect()
    assert tool is not None
    assert tool.paths == ("/opt/go/bin/go",)


def test_discover_tools_aggregates(monkeypatch):
    monkeypatch.setattr(
        "bal_sbx.discovery.tools.shutil.which",
        lambda name: "/opt/x/bin/" + name if name in {"node", "go"} else None,
    )
    monkeypatch.setattr("bal_sbx.discovery.tools.os.path.isfile", lambda _: False)
    monkeypatch.setattr("bal_sbx.discovery.tools.os.path.isdir", lambda _: False)
    monkeypatch.setattr(
        "bal_sbx.discovery.tools.os.path.expanduser",
        lambda p: "/no/such/path",
    )
    found = discover_tools()
    assert set(found) == {"node", "go"}


def test_discover_tools_filters_none():
    """Empty detector list ⇒ empty dict."""
    assert discover_tools(detectors=()) == {}


def test_default_permissions_do_not_include_write():
    """Discovered tools must never grant WRITE by default."""
    # Cargo (a directory-based detector) is the simplest to validate without
    # mocking — set up a real expanduser-resolvable cargo bin under tmp_path.
    import os

    class _FakeDetector:
        name = "fake"

        def detect(self):
            from bal_sbx.core.shared_tools import Permission, SharedTool
            return SharedTool(
                name=self.name,
                paths=("/usr/bin",),
                permissions=frozenset({Permission.READ, Permission.EXECUTE}),
            )

    found = discover_tools(detectors=(_FakeDetector(),))
    assert Permission.WRITE not in found["fake"].permissions
    del os
