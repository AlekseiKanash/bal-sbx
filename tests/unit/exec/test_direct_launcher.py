import os
from unittest.mock import MagicMock

import pytest

from bal_sbx.backends.user import UserSandbox
from bal_sbx.core.identity import SandboxIdentity
from bal_sbx.core.paths import PathLayout
from bal_sbx.exec.launcher import AgentLauncher, DirectLauncher, SandboxedLauncher
from bal_sbx.registry.json_file import JsonFileRegistry


LAYOUT = PathLayout(home_root="/home", registry_path="/tmp/r.json")


def test_exec_replace_writes_mode_unsafe_to_stderr(monkeypatch, capsys):
    launcher = DirectLauncher()
    monkeypatch.setattr(os, "execvpe", lambda *a, **kw: None)
    with pytest.raises(RuntimeError):
        launcher.exec_replace(["echo", "hi"])
    captured = capsys.readouterr()
    assert "MODE: UNSAFE" in captured.err


def test_exec_replace_calls_execvpe_with_argv_and_env(monkeypatch, capsys):
    launcher = DirectLauncher()
    captured: dict = {}

    def fake_execvpe(file, args, env):
        captured["file"] = file
        captured["args"] = list(args)
        captured["env"] = dict(env)

    monkeypatch.setattr(os, "execvpe", fake_execvpe)
    monkeypatch.setenv("HOST_ONLY", "yes")

    with pytest.raises(RuntimeError):
        launcher.exec_replace(["agent", "--x"], env_overrides={"FOO": "bar"})

    capsys.readouterr()  # drain stderr noise

    assert captured["file"] == "agent"
    assert captured["args"] == ["agent", "--x"]
    assert captured["env"]["HOST_ONLY"] == "yes"  # host env inherited (unsafe)
    assert captured["env"]["FOO"] == "bar"


def test_exec_replace_overrides_override_host(monkeypatch, capsys):
    launcher = DirectLauncher()
    captured: dict = {}
    monkeypatch.setattr(
        os,
        "execvpe",
        lambda f, a, env: captured.update(env=dict(env)),
    )
    monkeypatch.setenv("KEY", "host-value")
    with pytest.raises(RuntimeError):
        launcher.exec_replace(["agent"], env_overrides={"KEY": "override"})
    capsys.readouterr()
    assert captured["env"]["KEY"] == "override"


def test_run_announces_and_returns_exit_code(monkeypatch, capsys):
    launcher = DirectLauncher()
    monkeypatch.setattr(
        "bal_sbx.exec.launcher.subprocess.run",
        lambda *a, **kw: MagicMock(returncode=4),
    )
    assert launcher.run(["agent"]) == 4
    assert "MODE: UNSAFE" in capsys.readouterr().err


def test_run_does_not_raise_on_nonzero(monkeypatch, capsys):
    launcher = DirectLauncher()
    monkeypatch.setattr(
        "bal_sbx.exec.launcher.subprocess.run",
        lambda *a, **kw: MagicMock(returncode=1),
    )
    assert launcher.run(["agent"]) == 1
    capsys.readouterr()


def test_run_inherits_host_env_with_overrides(monkeypatch, capsys):
    launcher = DirectLauncher()
    captured: dict = {}

    def fake_run(argv, env=None, check=False):
        captured["argv"] = list(argv)
        captured["env"] = dict(env)
        return MagicMock(returncode=0)

    monkeypatch.setattr("bal_sbx.exec.launcher.subprocess.run", fake_run)
    monkeypatch.setenv("HOST_KEY", "1")
    launcher.run(["agent", "x"], env_overrides={"EXTRA": "yes"})
    capsys.readouterr()

    assert captured["argv"] == ["agent", "x"]
    assert captured["env"]["HOST_KEY"] == "1"
    assert captured["env"]["EXTRA"] == "yes"


# ---- structural protocol conformance -----------------------------------

def _run_via_protocol(launcher: AgentLauncher) -> int:
    return launcher.run(["true"])


def test_both_launchers_match_protocol_structurally(
    monkeypatch, fake_system_ops, tmp_path, capsys
):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    identity = SandboxIdentity.from_workspace(str(workspace), LAYOUT)
    sandbox = UserSandbox(identity, fake_system_ops)
    sandbox.create()
    registry = JsonFileRegistry(str(tmp_path / "registry.json"))

    sandboxed: AgentLauncher = SandboxedLauncher(sandbox, fake_system_ops, registry)
    direct: AgentLauncher = DirectLauncher()

    monkeypatch.setattr(
        "bal_sbx.exec.launcher.subprocess.run",
        lambda *a, **kw: MagicMock(returncode=0),
    )
    assert _run_via_protocol(sandboxed) == 0
    assert _run_via_protocol(direct) == 0
    capsys.readouterr()
