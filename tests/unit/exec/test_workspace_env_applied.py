"""End-to-end env precedence: CLI > workspace (per-sandbox) > tool env > defaults.

Source of truth for per-sandbox env is now the registry's `config.env`. The
single integration-style test asserting the three-tier precedence is
`test_precedence_cli_beats_workspace_beats_defaults` — keep precedence
assertions consolidated there.
"""

from __future__ import annotations

import os
from dataclasses import replace

import pytest

from bal_sbx.api import SandboxManager
from bal_sbx.core.config import SandboxConfig
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


def _set_workspace_env(manager: SandboxManager, ws: str, key: str, value: str) -> None:
    def _mutate(cfg: SandboxConfig) -> SandboxConfig:
        new_env = {**cfg.env, key: value}
        return replace(cfg, env=new_env)

    manager.update_config(ws, _mutate)


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
    manager = _manager(tmp_path, fake_system_ops)
    _set_workspace_env(manager, str(ws), "WS_KEY", "ws_value")

    launcher = manager.launcher(str(ws))
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
    manager = _manager(tmp_path, fake_system_ops)
    _set_workspace_env(manager, str(ws), "PATH", "/from/workspace")
    _set_workspace_env(manager, str(ws), "WS_ONLY", "ws")

    launcher = manager.launcher(str(ws))
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


def test_global_env_appears_in_argv(monkeypatch, tmp_path, fake_system_ops):
    ws = tmp_path / "ws"
    ws.mkdir()
    manager = _manager(tmp_path, fake_system_ops)
    manager._registry.set_global_config(SandboxConfig(env={"GLOBAL_KEY": "g"}))

    launcher = manager.launcher(str(ws))
    captured = _capture_argv(monkeypatch)
    with pytest.raises(RuntimeError):
        launcher.exec_replace(["agent"])

    env = _env_from_argv(captured["args"])
    assert env["GLOBAL_KEY"] == "g"


def test_workspace_env_overrides_global_env(monkeypatch, tmp_path, fake_system_ops):
    ws = tmp_path / "ws"
    ws.mkdir()
    manager = _manager(tmp_path, fake_system_ops)
    manager._registry.set_global_config(SandboxConfig(env={"K": "from_global"}))
    _set_workspace_env(manager, str(ws), "K", "from_workspace")

    launcher = manager.launcher(str(ws))
    captured = _capture_argv(monkeypatch)
    with pytest.raises(RuntimeError):
        launcher.exec_replace(["agent"])

    env = _env_from_argv(captured["args"])
    assert env["K"] == "from_workspace"


def test_launcher_picks_up_env_change_on_next_build(monkeypatch, tmp_path, fake_system_ops):
    """Each call to manager.launcher() re-resolves config."""
    ws = tmp_path / "ws"
    ws.mkdir()
    manager = _manager(tmp_path, fake_system_ops)
    _set_workspace_env(manager, str(ws), "FOO", "one")

    # First launcher uses "one".
    launcher = manager.launcher(str(ws))
    captured = _capture_argv(monkeypatch)
    with pytest.raises(RuntimeError):
        launcher.exec_replace(["agent"])
    assert _env_from_argv(captured["args"])["FOO"] == "one"

    # Mutate, build a fresh launcher, exec — sees the new value.
    _set_workspace_env(manager, str(ws), "FOO", "two")
    launcher2 = manager.launcher(str(ws))
    captured2 = _capture_argv(monkeypatch)
    with pytest.raises(RuntimeError):
        launcher2.exec_replace(["agent"])
    assert _env_from_argv(captured2["args"])["FOO"] == "two"


def test_legacy_workspace_config_migrated_on_first_use(monkeypatch, tmp_path, fake_system_ops):
    """A legacy `<ws>/.bal/config.json` containing `env` is copied into the registry."""
    import json

    ws = tmp_path / "ws"
    ws.mkdir()
    legacy_dir = ws / ".bal"
    legacy_dir.mkdir()
    (legacy_dir / "config.json").write_text(json.dumps({"env": {"LEGACY": "yes"}}))

    manager = _manager(tmp_path, fake_system_ops)
    launcher = manager.launcher(str(ws))
    captured = _capture_argv(monkeypatch)
    with pytest.raises(RuntimeError):
        launcher.exec_replace(["agent"])

    env = _env_from_argv(captured["args"])
    assert env["LEGACY"] == "yes"

    identity = manager.resolve(str(ws))
    stored = manager._registry.get(identity.id)
    assert stored is not None
    assert stored.config.env == {"LEGACY": "yes"}
