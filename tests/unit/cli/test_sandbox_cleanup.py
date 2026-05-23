"""Tests for `bal-sbx sandbox cleanup` and `SandboxManager.cleanup_stale`."""

from __future__ import annotations

import builtins

from bal_sbx.api import SandboxManager
from bal_sbx.cli.main import main
from bal_sbx.core.identity import SandboxIdentity
from bal_sbx.core.metadata import SandboxMetadata
from bal_sbx.core.paths import PathLayout
from bal_sbx.registry.json_file import JsonFileRegistry


def _layout(tmp_path) -> PathLayout:
    return PathLayout(
        home_root=str(tmp_path / "homes"),
        registry_path=str(tmp_path / "registry.json"),
    )


def _manager(tmp_path, fake_system_ops) -> SandboxManager:
    layout = _layout(tmp_path)
    return SandboxManager(
        system_ops=fake_system_ops,
        registry=JsonFileRegistry(layout.registry_path),
        path_layout=layout,
    )


def _register_missing_workspace(manager: SandboxManager, tmp_path) -> SandboxIdentity:
    ws_path = str(tmp_path / "gone")  # never created
    identity = SandboxIdentity.from_workspace(ws_path, manager._path_layout)
    manager._registry.put(
        identity.id,
        SandboxMetadata(
            workspace=identity.workspace,
            created_at="2026-05-23T10:00:00+00:00",
            last_used_at="2026-05-23T10:00:00+00:00",
        ),
    )
    return identity


def test_cleanup_stale_dry_run_returns_list_without_mutation(
    tmp_path, fake_system_ops
):
    manager = _manager(tmp_path, fake_system_ops)
    identity = _register_missing_workspace(manager, tmp_path)

    reports = manager.cleanup_stale(dry_run=True)

    assert [r.identity.id for r in reports] == [identity.id]
    # Registry unchanged.
    assert manager._registry.get(identity.id) is not None


def test_cleanup_stale_removes_entries_with_missing_workspace(
    tmp_path, fake_system_ops
):
    manager = _manager(tmp_path, fake_system_ops)
    identity = _register_missing_workspace(manager, tmp_path)

    # Add a healthy sandbox to confirm cleanup leaves it alone.
    ws_ok = tmp_path / "ok"
    ws_ok.mkdir()
    manager.get_or_create(str(ws_ok))

    reports = manager.cleanup_stale(dry_run=False)

    assert [r.identity.id for r in reports] == [identity.id]
    assert manager._registry.get(identity.id) is None
    # Healthy one still registered.
    ok_identity = manager.resolve(str(ws_ok))
    assert manager._registry.get(ok_identity.id) is not None


def test_cmd_cleanup_no_candidates_returns_zero(
    capsys, tmp_path, fake_system_ops
):
    manager = _manager(tmp_path, fake_system_ops)
    ws = tmp_path / "ws"
    ws.mkdir()
    manager.get_or_create(str(ws))

    rc = main(["sandbox", "cleanup"], manager_factory=lambda: manager)

    assert rc == 0
    assert "No stale sandboxes" in capsys.readouterr().out


def test_cmd_cleanup_prompts_and_proceeds_on_y(
    capsys, monkeypatch, tmp_path, fake_system_ops
):
    manager = _manager(tmp_path, fake_system_ops)
    identity = _register_missing_workspace(manager, tmp_path)

    monkeypatch.setattr(builtins, "input", lambda _prompt="": "y")

    rc = main(["sandbox", "cleanup"], manager_factory=lambda: manager)

    assert rc == 0
    assert manager._registry.get(identity.id) is None
    out = capsys.readouterr().out
    assert identity.id in out
    assert "Removed" in out


def test_cmd_cleanup_prompts_and_aborts_on_n(
    capsys, monkeypatch, tmp_path, fake_system_ops
):
    manager = _manager(tmp_path, fake_system_ops)
    identity = _register_missing_workspace(manager, tmp_path)

    monkeypatch.setattr(builtins, "input", lambda _prompt="": "n")

    rc = main(["sandbox", "cleanup"], manager_factory=lambda: manager)

    assert rc == 0
    assert manager._registry.get(identity.id) is not None
    assert "Aborted." in capsys.readouterr().out


def test_cmd_cleanup_yes_skips_prompt(
    capsys, monkeypatch, tmp_path, fake_system_ops
):
    manager = _manager(tmp_path, fake_system_ops)
    identity = _register_missing_workspace(manager, tmp_path)

    def _no_input(_prompt=""):
        raise AssertionError("input() should not be called when --yes is passed")

    monkeypatch.setattr(builtins, "input", _no_input)

    rc = main(["sandbox", "cleanup", "--yes"], manager_factory=lambda: manager)

    assert rc == 0
    assert manager._registry.get(identity.id) is None


def test_cmd_cleanup_dry_run_does_not_prompt_or_mutate(
    capsys, monkeypatch, tmp_path, fake_system_ops
):
    manager = _manager(tmp_path, fake_system_ops)
    identity = _register_missing_workspace(manager, tmp_path)

    def _no_input(_prompt=""):
        raise AssertionError("input() should not be called for --dry-run")

    monkeypatch.setattr(builtins, "input", _no_input)

    rc = main(["sandbox", "cleanup", "--dry-run"], manager_factory=lambda: manager)

    assert rc == 0
    assert manager._registry.get(identity.id) is not None
    out = capsys.readouterr().out
    assert identity.id in out
    assert "would remove" in out
