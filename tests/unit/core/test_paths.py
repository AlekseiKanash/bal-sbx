import os

import pytest

from bal_sbx.core.errors import PlatformUnsupported
from bal_sbx.core.paths import PathLayout


def test_default_on_linux(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    layout = PathLayout.default()
    assert layout.home_root == "/home"
    assert layout.registry_path == os.path.expanduser("~/.bal/sandboxes.json")


def test_default_on_darwin(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    layout = PathLayout.default()
    assert layout.home_root == "/Users"


def test_default_on_unsupported_platform(monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    with pytest.raises(PlatformUnsupported):
        PathLayout.default()


def test_home_for_and_workspace_link_for():
    layout = PathLayout(home_root="/home", registry_path="/tmp/r.json")
    assert layout.home_for("bal_abcdef") == "/home/bal_abcdef"
    assert layout.workspace_link_for("bal_abcdef") == "/home/bal_abcdef/workspace"


def test_layout_defaults():
    layout = PathLayout(home_root="/home", registry_path="/tmp/r.json")
    assert layout.workspace_config_dir == ".bal"


def test_layout_is_frozen():
    layout = PathLayout(home_root="/home", registry_path="/tmp/r.json")
    import dataclasses

    try:
        layout.home_root = "/elsewhere"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("PathLayout must be frozen")
