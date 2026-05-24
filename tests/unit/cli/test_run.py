"""Tests for the run-in-sandbox dispatch path (`bal-sbx <cmd>`).

Two-layer strategy:

- Fake-manager tests use `MagicMock` to verify which launcher is built and
  what argv is handed to `exec_replace`. These cover dispatch logic.
- Real-manager tests use `fake_system_ops` from `tests/conftest.py` to exercise
  auto-create through `SandboxManager.launcher()` end-to-end.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from bal_sbx.api import SandboxManager, SandboxMode
from bal_sbx.cli.main import main
from bal_sbx.core.paths import PathLayout
from bal_sbx.registry.json_file import JsonFileRegistry


def _fake_manager(launcher: MagicMock) -> MagicMock:
    manager = MagicMock()
    manager.launcher.return_value = launcher
    manager.unsafe.return_value = launcher
    return manager


def _fake_launcher() -> MagicMock:
    launcher = MagicMock()
    launcher.exec_replace.side_effect = SystemExit(0)
    return launcher


def _real_manager(tmp_path, fake_system_ops) -> SandboxManager:
    layout = PathLayout(
        home_root=str(tmp_path / "homes"),
        registry_path=str(tmp_path / "registry.json"),
    )
    return SandboxManager(
        system_ops=fake_system_ops,
        registry=JsonFileRegistry(layout.registry_path),
        path_layout=layout,
    )


def test_single_positional_runs_in_safe_sandbox(monkeypatch, tmp_path):
    launcher = _fake_launcher()
    manager = _fake_manager(launcher)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as exc:
        main(["sh"], manager_factory=lambda: manager)

    assert exc.value.code == 0
    manager.launcher.assert_called_once()
    _, kwargs = manager.launcher.call_args
    assert kwargs["mode"] is SandboxMode.SAFE
    manager.unsafe.assert_not_called()
    launcher.exec_replace.assert_called_once_with(["sh", "-c", "sh"])


def test_multi_word_quoted_string_is_passed_to_sh_dash_c(monkeypatch, tmp_path):
    launcher = _fake_launcher()
    manager = _fake_manager(launcher)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        main(["bash probe.sh"], manager_factory=lambda: manager)

    launcher.exec_replace.assert_called_once_with(
        ["sh", "-c", "bash probe.sh"]
    )


def test_unsafe_flag_uses_direct_launcher_and_prints_banner(
    capsys, monkeypatch, tmp_path
):
    launcher = _fake_launcher()
    manager = _fake_manager(launcher)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        main(["--unsafe", "claude"], manager_factory=lambda: manager)

    err = capsys.readouterr().err
    assert "UNSAFE" in err
    manager.unsafe.assert_called_once()
    manager.launcher.assert_not_called()
    launcher.exec_replace.assert_called_once_with(["sh", "-c", "claude"])


def test_explicit_workspace_overrides_cwd(monkeypatch, tmp_path):
    launcher = _fake_launcher()
    manager = _fake_manager(launcher)
    target = tmp_path / "ws"
    target.mkdir()
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        main(
            ["--workspace", str(target), "sh"],
            manager_factory=lambda: manager,
        )

    workspace_arg = manager.launcher.call_args[0][0]
    assert workspace_arg == os.path.realpath(str(target))


def test_workspace_with_equals_form(monkeypatch, tmp_path):
    launcher = _fake_launcher()
    manager = _fake_manager(launcher)
    target = tmp_path / "ws"
    target.mkdir()
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        main(
            [f"--workspace={target}", "sh"],
            manager_factory=lambda: manager,
        )

    workspace_arg = manager.launcher.call_args[0][0]
    assert workspace_arg == os.path.realpath(str(target))


def test_workspace_inferred_from_cwd(monkeypatch, tmp_path):
    launcher = _fake_launcher()
    manager = _fake_manager(launcher)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        main(["sh"], manager_factory=lambda: manager)

    workspace_arg = manager.launcher.call_args[0][0]
    assert workspace_arg == os.path.realpath(str(tmp_path))


def test_dash_dash_separator_is_consumed(monkeypatch, tmp_path):
    launcher = _fake_launcher()
    manager = _fake_manager(launcher)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        main(["--unsafe", "--", "claude"], manager_factory=lambda: manager)

    launcher.exec_replace.assert_called_once_with(["sh", "-c", "claude"])


def test_two_positional_args_returns_usage_error(capsys, monkeypatch, tmp_path):
    launcher = _fake_launcher()
    manager = _fake_manager(launcher)
    monkeypatch.chdir(tmp_path)

    rc = main(["bash", "probe.sh"], manager_factory=lambda: manager)
    assert rc == 2
    err = capsys.readouterr().err
    assert "usage" in err.lower()
    launcher.exec_replace.assert_not_called()


def test_unknown_flag_returns_usage_error(capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    rc = main(["--nope", "sh"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "usage" in err.lower()


def test_bare_workspace_flag_returns_usage_error(capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    rc = main(["--workspace"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "usage" in err.lower()


def test_auto_create_writes_registry_entry(
    monkeypatch, tmp_path, fake_system_ops
):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    manager = _real_manager(tmp_path, fake_system_ops)

    monkeypatch.setattr(
        "bal_sbx.exec.launcher.SandboxedLauncher.exec_replace",
        lambda self, cmd, env_overrides=None: (_ for _ in ()).throw(SystemExit(0)),
    )

    with pytest.raises(SystemExit) as exc:
        main(["sh"], manager_factory=lambda: manager)
    assert exc.value.code == 0

    identity = manager.resolve(str(workspace))
    assert manager._registry.get(identity.id) is not None
