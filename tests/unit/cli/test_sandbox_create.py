"""Tests for `bal-sbx sandbox create`."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from bal_sbx.cli.main import main
from bal_sbx.core.identity import SandboxIdentity


def _identity(workspace: str) -> SandboxIdentity:
    return SandboxIdentity(
        id="bal_test01",
        user="bal_test01",
        workspace=workspace,
        home="/Users/bal_test01",
        workspace_link="/Users/bal_test01/workspace",
    )


def _fake_manager_for(workspace: str) -> MagicMock:
    sandbox = MagicMock()
    sandbox.identity = _identity(workspace)
    manager = MagicMock()
    manager.get_or_create.return_value = sandbox
    return manager


def test_sandbox_create_calls_get_or_create_with_resolved_workspace(
    capsys, monkeypatch, tmp_path
):
    target = tmp_path / "ws"
    target.mkdir()
    monkeypatch.chdir(tmp_path)

    manager = _fake_manager_for(os.path.realpath(str(target)))
    rc = main(
        ["sandbox", "create", "--workspace", str(target)],
        manager_factory=lambda: manager,
    )

    assert rc == 0
    manager.get_or_create.assert_called_once_with(
        os.path.realpath(str(target)), kind="user"
    )
    out = capsys.readouterr().out
    assert "bal_test01" in out
    assert "user=bal_test01" in out
    assert "home=/Users/bal_test01" in out


def test_sandbox_create_defaults_to_inferred_workspace(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    manager = _fake_manager_for(os.path.realpath(str(tmp_path)))

    rc = main(["sandbox", "create"], manager_factory=lambda: manager)

    assert rc == 0
    manager.get_or_create.assert_called_once_with(
        os.path.realpath(str(tmp_path)), kind="user"
    )


def test_sandbox_create_rejects_unknown_kind(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(
            ["sandbox", "create", "--type", "docker"],
            manager_factory=lambda: MagicMock(),
        )
    assert exc.value.code != 0
