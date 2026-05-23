"""Tests for `bal-sbx sandbox env`."""

from __future__ import annotations

import json

from bal_sbx.api import SandboxManager
from bal_sbx.cli.main import main
from bal_sbx.core.paths import PathLayout
from bal_sbx.registry.json_file import JsonFileRegistry


def _manager(tmp_path, fake_system_ops) -> SandboxManager:
    layout = PathLayout(
        home_root=str(tmp_path / "homes"),
        registry_path=str(tmp_path / "registry.json"),
    )
    return SandboxManager(
        system_ops=fake_system_ops,
        registry=JsonFileRegistry(layout.registry_path),
        path_layout=layout,
    )


def _workspace(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    return ws


def test_env_set_writes_workspace_config(tmp_path, fake_system_ops):
    ws = _workspace(tmp_path)
    manager = _manager(tmp_path, fake_system_ops)
    rc = main(
        ["sandbox", "env", "--workspace", str(ws), "FOO", "bar"],
        manager_factory=lambda: manager,
    )
    assert rc == 0
    cfg_path = ws / ".bal" / "config.json"
    assert cfg_path.exists()
    raw = json.loads(cfg_path.read_text())
    assert raw["env"]["FOO"] == "bar"


def test_env_get_returns_value_and_zero_exit(capsys, tmp_path, fake_system_ops):
    ws = _workspace(tmp_path)
    manager = _manager(tmp_path, fake_system_ops)
    main(
        ["sandbox", "env", "--workspace", str(ws), "FOO", "bar"],
        manager_factory=lambda: manager,
    )
    capsys.readouterr()

    rc = main(
        ["sandbox", "env", "--workspace", str(ws), "FOO"],
        manager_factory=lambda: manager,
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert out.strip() == "bar"


def test_env_get_missing_key_exits_one(tmp_path, fake_system_ops):
    ws = _workspace(tmp_path)
    manager = _manager(tmp_path, fake_system_ops)
    rc = main(
        ["sandbox", "env", "--workspace", str(ws), "ABSENT"],
        manager_factory=lambda: manager,
    )
    assert rc == 1


def test_env_list_prints_all_keys_sorted(capsys, tmp_path, fake_system_ops):
    ws = _workspace(tmp_path)
    manager = _manager(tmp_path, fake_system_ops)
    main(
        ["sandbox", "env", "--workspace", str(ws), "FOO", "bar"],
        manager_factory=lambda: manager,
    )
    main(
        ["sandbox", "env", "--workspace", str(ws), "BAZ", "qux"],
        manager_factory=lambda: manager,
    )
    capsys.readouterr()

    rc = main(
        ["sandbox", "env", "--workspace", str(ws)],
        manager_factory=lambda: manager,
    )
    assert rc == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines == ["BAZ=qux", "FOO=bar"]


def test_env_unset_removes_key(tmp_path, fake_system_ops):
    ws = _workspace(tmp_path)
    manager = _manager(tmp_path, fake_system_ops)
    main(
        ["sandbox", "env", "--workspace", str(ws), "FOO", "bar"],
        manager_factory=lambda: manager,
    )
    rc = main(
        ["sandbox", "env", "--workspace", str(ws), "--unset", "FOO"],
        manager_factory=lambda: manager,
    )
    assert rc == 0

    rc = main(
        ["sandbox", "env", "--workspace", str(ws), "FOO"],
        manager_factory=lambda: manager,
    )
    assert rc == 1


def test_env_does_not_create_sandbox(tmp_path, fake_system_ops):
    """`env` is registry-free: managing config must not provision users/homes."""
    ws = _workspace(tmp_path)
    manager = _manager(tmp_path, fake_system_ops)
    main(
        ["sandbox", "env", "--workspace", str(ws), "FOO", "bar"],
        manager_factory=lambda: manager,
    )
    assert fake_system_ops.users.users == set()
    assert manager._registry.list() == []
