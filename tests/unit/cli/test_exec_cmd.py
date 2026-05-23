"""Tests for `bal-sbx exec`.

Strategy: inject a fake `SandboxManager` via `manager_factory` so we never
hit `os.execvp`. The fake's `exec_replace` raises `SystemExit(0)` to mimic
the no-return contract; tests assert it was called with the right argv.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from bal_sbx.api import SandboxMode
from bal_sbx.cli.main import main
from bal_sbx.cli.workspace import resolve_workspace


def _fake_manager(launcher: MagicMock) -> MagicMock:
    manager = MagicMock()
    manager.launcher.return_value = launcher
    manager.unsafe.return_value = launcher
    return manager


def _fake_launcher() -> MagicMock:
    launcher = MagicMock()
    launcher.exec_replace.side_effect = SystemExit(0)
    return launcher


def test_exec_safe_uses_sandboxed_launcher(monkeypatch, tmp_path):
    launcher = _fake_launcher()
    manager = _fake_manager(launcher)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as exc:
        main(["exec", "--", "echo", "hi"], manager_factory=lambda: manager)

    assert exc.value.code == 0
    manager.launcher.assert_called_once()
    _, kwargs = manager.launcher.call_args
    assert kwargs["mode"] is SandboxMode.SAFE
    manager.unsafe.assert_not_called()
    launcher.exec_replace.assert_called_once_with(["echo", "hi"])


def test_exec_unsafe_uses_direct_launcher_and_emits_banner(
    capsys, monkeypatch, tmp_path
):
    launcher = _fake_launcher()
    manager = _fake_manager(launcher)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        main(
            ["exec", "--unsafe", "--", "echo", "hi"],
            manager_factory=lambda: manager,
        )

    err = capsys.readouterr().err
    assert "UNSAFE" in err
    manager.unsafe.assert_called_once()
    manager.launcher.assert_not_called()
    launcher.exec_replace.assert_called_once_with(["echo", "hi"])


def test_exec_explicit_workspace_is_canonicalized(monkeypatch, tmp_path):
    launcher = _fake_launcher()
    manager = _fake_manager(launcher)
    target = tmp_path / "ws"
    target.mkdir()
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        main(
            ["exec", "--workspace", str(target), "--", "true"],
            manager_factory=lambda: manager,
        )

    workspace_arg = manager.launcher.call_args[0][0]
    assert workspace_arg == os.path.realpath(str(target))


def test_exec_infers_workspace_from_dot_bal_marker(monkeypatch, tmp_path):
    """With `.bal/` at the workspace root, a deeply-nested cwd still resolves up."""
    (tmp_path / ".bal").mkdir()
    deep = tmp_path / "sub" / "deeper"
    deep.mkdir(parents=True)
    monkeypatch.chdir(deep)

    launcher = _fake_launcher()
    manager = _fake_manager(launcher)

    with pytest.raises(SystemExit):
        main(["exec", "--", "true"], manager_factory=lambda: manager)

    workspace_arg = manager.launcher.call_args[0][0]
    assert workspace_arg == os.path.realpath(str(tmp_path))


def test_exec_without_command_returns_usage_error(capsys, monkeypatch, tmp_path):
    launcher = _fake_launcher()
    manager = _fake_manager(launcher)
    monkeypatch.chdir(tmp_path)

    rc = main(["exec"], manager_factory=lambda: manager)
    assert rc == 2
    err = capsys.readouterr().err
    assert "usage" in err.lower()
    launcher.exec_replace.assert_not_called()


def test_resolve_workspace_falls_back_to_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert resolve_workspace(None) == os.path.realpath(str(tmp_path))


def test_resolve_workspace_canonicalizes_explicit_path(tmp_path):
    target = tmp_path / "ws"
    target.mkdir()
    assert resolve_workspace(str(target)) == os.path.realpath(str(target))
