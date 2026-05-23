"""Integration: SandboxManager honors Settings on auto-detection."""

from __future__ import annotations

from bal_sbx.api import SandboxManager
from bal_sbx.config.settings import Settings
from bal_sbx.core.paths import PathLayout
from bal_sbx.registry.json_file import JsonFileRegistry
from bal_sbx.system.privilege import SudoBroker, SudoPerOpBroker


def test_settings_privilege_mode_per_operation_picks_per_op_broker():
    manager = SandboxManager(
        settings=Settings(privilege_mode="per_operation"),
    )
    assert isinstance(manager._system_ops.privilege, SudoPerOpBroker)


def test_settings_privilege_mode_cached_picks_cached_broker():
    manager = SandboxManager(
        settings=Settings(privilege_mode="cached"),
    )
    assert isinstance(manager._system_ops.privilege, SudoBroker)


def test_settings_registry_path_overrides_layout_default(tmp_path, fake_system_ops):
    custom = tmp_path / "custom.json"
    layout = PathLayout(
        home_root=str(tmp_path / "homes"),
        registry_path=str(tmp_path / "ignored.json"),
    )
    manager = SandboxManager(
        system_ops=fake_system_ops,
        path_layout=layout,
        settings=Settings(registry_path=str(custom)),
    )
    assert manager._registry._path == str(custom)


def test_settings_default_used_when_provided_explicitly(tmp_path, fake_system_ops):
    """`settings=` is honored verbatim; no fallthrough to Settings.load()."""
    layout = PathLayout(
        home_root=str(tmp_path / "homes"),
        registry_path=str(tmp_path / "r.json"),
    )
    explicit = Settings(privilege_mode="cached", registry_path=None)
    manager = SandboxManager(
        system_ops=fake_system_ops,
        registry=JsonFileRegistry(str(tmp_path / "r.json")),
        path_layout=layout,
        settings=explicit,
    )
    assert manager._settings is explicit
