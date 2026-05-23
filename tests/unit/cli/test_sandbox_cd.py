"""Tests for `bal-sbx sandbox cd`."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bal_sbx.api import SandboxManager
from bal_sbx.cli.main import main
from bal_sbx.core.paths import PathLayout
from bal_sbx.registry.json_file import JsonFileRegistry


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


def test_sandbox_cd_errors_when_not_registered(
    capsys, monkeypatch, tmp_path, fake_system_ops
):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    manager = _real_manager(tmp_path, fake_system_ops)

    rc = main(["sandbox", "cd"], manager_factory=lambda: manager)

    assert rc == 2
    err = capsys.readouterr().err
    assert "SandboxNotFound" in err
    assert "sandbox create" in err


def test_sandbox_cd_invokes_execvp_with_sudo_as_user(
    monkeypatch, tmp_path, fake_system_ops
):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    manager = _real_manager(tmp_path, fake_system_ops)
    manager.get_or_create(str(workspace))

    execvp = MagicMock(side_effect=SystemExit(0))
    monkeypatch.setattr("os.execvp", execvp)
    monkeypatch.chdir(workspace)

    with pytest.raises(SystemExit) as exc:
        main(["sandbox", "cd"], manager_factory=lambda: manager)
    assert exc.value.code == 0

    execvp.assert_called_once()
    file, argv = execvp.call_args.args
    assert file == "sudo"
    identity = manager.resolve(str(workspace))
    assert argv[0] == "sudo"
    assert argv[1] == "-u"
    assert argv[2] == identity.user
    assert "-H" in argv
