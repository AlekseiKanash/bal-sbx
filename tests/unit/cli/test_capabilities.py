"""Tests for `bal-sbx capabilities`."""

from __future__ import annotations

import sys

from bal_sbx.api import SandboxManager
from bal_sbx.cli.main import main
from bal_sbx.core.paths import PathLayout
from bal_sbx.registry.json_file import JsonFileRegistry


def _manager(fake_system_ops, tmp_path) -> SandboxManager:
    layout = PathLayout(
        home_root=str(tmp_path / "homes"),
        registry_path=str(tmp_path / "registry.json"),
    )
    return SandboxManager(
        system_ops=fake_system_ops,
        registry=JsonFileRegistry(layout.registry_path),
        path_layout=layout,
    )


def test_capabilities_prints_all_keys(capsys, fake_system_ops, tmp_path):
    manager = _manager(fake_system_ops, tmp_path)
    rc = main(["capabilities"], manager_factory=lambda: manager)
    assert rc == 0
    out = capsys.readouterr().out
    assert f"platform: {sys.platform}" in out
    assert "can_sudo:" in out
    assert "acl_supported:" in out


def test_capabilities_does_not_print_reason_when_supported(
    capsys, fake_system_ops, tmp_path
):
    manager = _manager(fake_system_ops, tmp_path)
    main(["capabilities"], manager_factory=lambda: manager)
    out = capsys.readouterr().out
    # On linux/darwin, no unsupported_reason should appear.
    assert "unsupported_reason" not in out
