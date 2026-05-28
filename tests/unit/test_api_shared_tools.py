"""SandboxManager integration with shared-tool config resolution."""

from __future__ import annotations

import os
from dataclasses import replace

import pytest

from bal_sbx.api import SandboxManager
from bal_sbx.core.config import SandboxConfig
from bal_sbx.core.paths import PathLayout
from bal_sbx.core.shared_tools import Permission, SharedTool
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
    pairs = args[6:-1]
    return dict(p.split("=", 1) for p in pairs)


def _brew_tool(bin_path: str, extras: tuple[str, ...] = (), env: dict | None = None) -> SharedTool:
    return SharedTool(
        name="brew",
        paths=(bin_path, *extras),
        permissions=frozenset({Permission.READ, Permission.EXECUTE}),
        env=env or {},
    )


def test_get_or_create_grants_shared_tool_acls(tmp_path, fake_system_ops):
    bin_dir = tmp_path / "brew_bin"
    bin_dir.mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    manager = _manager(tmp_path, fake_system_ops)
    manager._registry.set_global_config(
        SandboxConfig(shared_tools={"brew": _brew_tool(str(bin_dir))})
    )

    sandbox = manager.get_or_create(str(ws))
    assert fake_system_ops.acl.is_granted(
        str(bin_dir),
        sandbox.identity.user,
        frozenset({Permission.READ, Permission.EXECUTE}),
    )


def test_get_or_create_warns_on_missing_path(tmp_path, fake_system_ops):
    ws = tmp_path / "ws"
    ws.mkdir()
    manager = _manager(tmp_path, fake_system_ops)
    manager._registry.set_global_config(
        SandboxConfig(shared_tools={"brew": _brew_tool("/does/not/exist/bin")})
    )

    with pytest.warns(UserWarning, match="brew.*/does/not/exist/bin.*not found"):
        manager.get_or_create(str(ws))


def test_launcher_adds_shared_tool_paths_to_PATH(monkeypatch, tmp_path, fake_system_ops):
    bin_dir = tmp_path / "brew" / "bin"
    bin_dir.mkdir(parents=True)
    ws = tmp_path / "ws"
    ws.mkdir()
    manager = _manager(tmp_path, fake_system_ops)
    manager._registry.set_global_config(
        SandboxConfig(shared_tools={"brew": _brew_tool(str(bin_dir))})
    )

    launcher = manager.launcher(str(ws))
    captured = _capture_argv(monkeypatch)
    with pytest.raises(RuntimeError):
        launcher.exec_replace(["agent"])

    env = _env_from_argv(captured["args"])
    assert env["PATH"].startswith(f"{bin_dir}:")


def test_launcher_skips_non_bin_paths_from_PATH(monkeypatch, tmp_path, fake_system_ops):
    bin_dir = tmp_path / "brew" / "bin"
    bin_dir.mkdir(parents=True)
    cellar = tmp_path / "brew" / "Cellar"
    cellar.mkdir(parents=True)
    ws = tmp_path / "ws"
    ws.mkdir()
    manager = _manager(tmp_path, fake_system_ops)
    manager._registry.set_global_config(
        SandboxConfig(
            shared_tools={
                "brew": _brew_tool(str(bin_dir), extras=(str(cellar),)),
            }
        )
    )

    launcher = manager.launcher(str(ws))
    captured = _capture_argv(monkeypatch)
    with pytest.raises(RuntimeError):
        launcher.exec_replace(["agent"])

    env = _env_from_argv(captured["args"])
    # bin dir on PATH, Cellar only ACL-granted
    assert str(bin_dir) in env["PATH"]
    assert str(cellar) not in env["PATH"]
    # ACL still granted on both
    assert fake_system_ops.acl.is_granted(str(bin_dir), launcher._sandbox.identity.user)
    assert fake_system_ops.acl.is_granted(str(cellar), launcher._sandbox.identity.user)


def test_launcher_includes_tool_env(monkeypatch, tmp_path, fake_system_ops):
    bin_dir = tmp_path / "brew" / "bin"
    bin_dir.mkdir(parents=True)
    ws = tmp_path / "ws"
    ws.mkdir()
    manager = _manager(tmp_path, fake_system_ops)
    manager._registry.set_global_config(
        SandboxConfig(
            shared_tools={
                "brew": _brew_tool(str(bin_dir), env={"HOMEBREW_PREFIX": "/opt/homebrew"})
            }
        )
    )

    launcher = manager.launcher(str(ws))
    captured = _capture_argv(monkeypatch)
    with pytest.raises(RuntimeError):
        launcher.exec_replace(["agent"])

    env = _env_from_argv(captured["args"])
    assert env["HOMEBREW_PREFIX"] == "/opt/homebrew"


def test_per_sandbox_tool_replaces_global_by_name(tmp_path, fake_system_ops):
    global_bin = tmp_path / "global_bin"
    global_bin.mkdir()
    workspace_bin = tmp_path / "workspace_bin"
    workspace_bin.mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    manager = _manager(tmp_path, fake_system_ops)
    manager._registry.set_global_config(
        SandboxConfig(shared_tools={"brew": _brew_tool(str(global_bin))})
    )

    def _override(cfg: SandboxConfig) -> SandboxConfig:
        return replace(
            cfg, shared_tools={"brew": _brew_tool(str(workspace_bin))}
        )

    manager.update_config(str(ws), _override)
    sandbox = manager.get_or_create(str(ws))
    user = sandbox.identity.user
    assert fake_system_ops.acl.is_granted(str(workspace_bin), user)
    assert not fake_system_ops.acl.is_granted(str(global_bin), user)


def test_destroy_revokes_shared_tool_acls(tmp_path, fake_system_ops):
    bin_dir = tmp_path / "brew_bin"
    bin_dir.mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    manager = _manager(tmp_path, fake_system_ops)
    manager._registry.set_global_config(
        SandboxConfig(shared_tools={"brew": _brew_tool(str(bin_dir))})
    )
    sandbox = manager.get_or_create(str(ws))
    user = sandbox.identity.user
    assert fake_system_ops.acl.is_granted(str(bin_dir), user)

    manager.destroy(str(ws))
    assert not fake_system_ops.acl.is_granted(str(bin_dir), user)


def test_second_get_or_create_self_heals_after_adding_tool(tmp_path, fake_system_ops):
    bin_dir = tmp_path / "brew_bin"
    bin_dir.mkdir()
    extra_bin = tmp_path / "node_bin"
    extra_bin.mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    manager = _manager(tmp_path, fake_system_ops)
    manager._registry.set_global_config(
        SandboxConfig(shared_tools={"brew": _brew_tool(str(bin_dir))})
    )
    sandbox = manager.get_or_create(str(ws))
    user = sandbox.identity.user
    assert not fake_system_ops.acl.is_granted(str(extra_bin), user)

    # User adds a new tool to global config, runs again.
    manager._registry.set_global_config(
        SandboxConfig(
            shared_tools={
                "brew": _brew_tool(str(bin_dir)),
                "node": _brew_tool(str(extra_bin)),
            }
        )
    )
    manager.get_or_create(str(ws))
    assert fake_system_ops.acl.is_granted(str(extra_bin), user)
