"""Tests for `bal-sbx sandbox env` — operates on the registry's config sections."""

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


def test_env_set_writes_per_sandbox_config(tmp_path, fake_system_ops):
    ws = _workspace(tmp_path)
    manager = _manager(tmp_path, fake_system_ops)
    rc = main(
        ["sandbox", "env", "--workspace", str(ws), "FOO", "bar"],
        manager_factory=lambda: manager,
    )
    assert rc == 0
    identity = manager.resolve(str(ws))
    stored = manager._registry.get(identity.id)
    assert stored is not None
    assert stored.config.env == {"FOO": "bar"}


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


def test_env_does_not_provision_user_or_home(tmp_path, fake_system_ops):
    """env is a config-only operation: no user/home/ACL provisioning."""
    ws = _workspace(tmp_path)
    manager = _manager(tmp_path, fake_system_ops)
    main(
        ["sandbox", "env", "--workspace", str(ws), "FOO", "bar"],
        manager_factory=lambda: manager,
    )
    assert fake_system_ops.users.users == set()
    # The registry entry exists (so config can be persisted) but the
    # sandbox itself was never provisioned.
    identity = manager.resolve(str(ws))
    stored = manager._registry.get(identity.id)
    assert stored is not None
    assert not fake_system_ops.home.exists(identity.home)


def test_env_global_set_writes_global_config(tmp_path, fake_system_ops):
    manager = _manager(tmp_path, fake_system_ops)
    rc = main(
        ["sandbox", "env", "--global", "EDITOR", "vim"],
        manager_factory=lambda: manager,
    )
    assert rc == 0
    assert manager._registry.global_config().env == {"EDITOR": "vim"}


def test_env_global_get_returns_value(capsys, tmp_path, fake_system_ops):
    manager = _manager(tmp_path, fake_system_ops)
    main(["sandbox", "env", "--global", "EDITOR", "vim"], manager_factory=lambda: manager)
    capsys.readouterr()

    rc = main(["sandbox", "env", "--global", "EDITOR"], manager_factory=lambda: manager)
    assert rc == 0
    assert capsys.readouterr().out.strip() == "vim"


def test_env_global_list_only_shows_global_keys(capsys, tmp_path, fake_system_ops):
    ws = _workspace(tmp_path)
    manager = _manager(tmp_path, fake_system_ops)
    main(["sandbox", "env", "--global", "GK", "gv"], manager_factory=lambda: manager)
    main(
        ["sandbox", "env", "--workspace", str(ws), "WK", "wv"],
        manager_factory=lambda: manager,
    )
    capsys.readouterr()

    main(["sandbox", "env", "--global"], manager_factory=lambda: manager)
    out = capsys.readouterr().out.splitlines()
    assert out == ["GK=gv"]


def test_env_global_unset_removes_key(tmp_path, fake_system_ops):
    manager = _manager(tmp_path, fake_system_ops)
    main(["sandbox", "env", "--global", "EDITOR", "vim"], manager_factory=lambda: manager)
    rc = main(
        ["sandbox", "env", "--global", "--unset", "EDITOR"],
        manager_factory=lambda: manager,
    )
    assert rc == 0
    assert manager._registry.global_config().env == {}


def test_env_per_sandbox_does_not_affect_global(tmp_path, fake_system_ops):
    ws = _workspace(tmp_path)
    manager = _manager(tmp_path, fake_system_ops)
    main(["sandbox", "env", "--global", "K", "global"], manager_factory=lambda: manager)
    main(
        ["sandbox", "env", "--workspace", str(ws), "K", "workspace"],
        manager_factory=lambda: manager,
    )
    assert manager._registry.global_config().env == {"K": "global"}
    identity = manager.resolve(str(ws))
    assert manager._registry.get(identity.id).config.env == {"K": "workspace"}


def test_env_on_disk_file_is_the_registry(tmp_path, fake_system_ops):
    """Sanity: the storage is sandboxes.json, not a per-workspace file."""
    ws = _workspace(tmp_path)
    manager = _manager(tmp_path, fake_system_ops)
    main(
        ["sandbox", "env", "--workspace", str(ws), "FOO", "bar"],
        manager_factory=lambda: manager,
    )
    legacy = ws / ".bal" / "config.json"
    assert not legacy.exists()
    registry_path = tmp_path / "registry.json"
    raw = json.loads(registry_path.read_text())
    assert "sandboxes" in raw
    only_entry = next(iter(raw["sandboxes"].values()))
    assert only_entry["config"]["env"] == {"FOO": "bar"}
