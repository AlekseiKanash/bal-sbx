"""End-to-end env precedence: CLI > workspace > defaults.

The single integration-style test asserting the three-tier precedence is
`test_precedence_cli_beats_workspace_beats_defaults`. Keep precedence
assertions consolidated there — see step 12.
"""

from __future__ import annotations

import os

import pytest

from bal_sbx.api import SandboxManager
from bal_sbx.config.workspace import WorkspaceConfig
from bal_sbx.core.paths import PathLayout
from bal_sbx.registry.json_file import JsonFileRegistry


def _layout(tmp_path) -> PathLayout:
    return PathLayout(
        home_root=str(tmp_path / "homes"),
        registry_path=str(tmp_path / "registry.json"),
    )


def _manager(tmp_path, fake_system_ops) -> SandboxManager:
    return SandboxManager(
        system_ops=fake_system_ops,
        registry=JsonFileRegistry(str(tmp_path / "registry.json")),
        path_layout=_layout(tmp_path),
    )


def _capture_argv(monkeypatch) -> dict:
    captured: dict = {}
    monkeypatch.setattr(
        os, "execvp", lambda _f, args: captured.setdefault("args", list(args))
    )
    return captured


def _env_from_argv(args: list[str]) -> dict[str, str]:
    # argv = ["sudo", "-u", USER, "-H", "env", "-i", *KEY=VAL pairs, *cmd]
    # The trailing cmd in these tests is a single token, so strip the last 1.
    pairs = args[6:-1]
    return dict(p.split("=", 1) for p in pairs)


def test_workspace_env_appears_in_argv(monkeypatch, tmp_path, fake_system_ops):
    ws = tmp_path / "ws"
    ws.mkdir()
    WorkspaceConfig(str(ws), _layout(tmp_path)).set_env("WS_KEY", "ws_value")

    launcher = _manager(tmp_path, fake_system_ops).launcher(str(ws))
    captured = _capture_argv(monkeypatch)
    with pytest.raises(RuntimeError):
        launcher.exec_replace(["agent"])

    env = _env_from_argv(captured["args"])
    assert env["WS_KEY"] == "ws_value"


def test_no_workspace_env_does_not_break_defaults(monkeypatch, tmp_path, fake_system_ops):
    ws = tmp_path / "ws"
    ws.mkdir()

    launcher = _manager(tmp_path, fake_system_ops).launcher(str(ws))
    captured = _capture_argv(monkeypatch)
    with pytest.raises(RuntimeError):
        launcher.exec_replace(["agent"])

    env = _env_from_argv(captured["args"])
    # Defaults still present, no leftover workspace keys.
    assert env["HOME"]
    assert "WS_KEY" not in env


def test_precedence_cli_beats_workspace_beats_defaults(
    monkeypatch, tmp_path, fake_system_ops
):
    """The centerpiece three-tier precedence assertion."""
    ws = tmp_path / "ws"
    ws.mkdir()
    cfg = WorkspaceConfig(str(ws), _layout(tmp_path))
    # workspace overrides a default (PATH) and contributes a unique key
    cfg.set_env("PATH", "/from/workspace")
    cfg.set_env("WS_ONLY", "ws")

    launcher = _manager(tmp_path, fake_system_ops).launcher(str(ws))
    captured = _capture_argv(monkeypatch)
    with pytest.raises(RuntimeError):
        launcher.exec_replace(
            ["agent"],
            env_overrides={"PATH": "/from/cli", "CLI_ONLY": "cli"},
        )

    env = _env_from_argv(captured["args"])
    # CLI wins over workspace
    assert env["PATH"] == "/from/cli"
    # Workspace key survives when no CLI override exists for it
    assert env["WS_ONLY"] == "ws"
    # CLI-only key present
    assert env["CLI_ONLY"] == "cli"
    # Identity keys still set by defaults layer
    assert env["BAL_SANDBOX_WORKSPACE"] == os.path.realpath(str(ws))


def test_workspace_env_read_freshly_per_launch(monkeypatch, tmp_path, fake_system_ops):
    """Mutating the workspace config after launcher construction is observed."""
    ws = tmp_path / "ws"
    ws.mkdir()
    cfg = WorkspaceConfig(str(ws), _layout(tmp_path))
    cfg.set_env("FOO", "one")

    launcher = _manager(tmp_path, fake_system_ops).launcher(str(ws))
    cfg.set_env("FOO", "two")  # mutate after launcher build

    captured = _capture_argv(monkeypatch)
    with pytest.raises(RuntimeError):
        launcher.exec_replace(["agent"])
    env = _env_from_argv(captured["args"])
    assert env["FOO"] == "two"
