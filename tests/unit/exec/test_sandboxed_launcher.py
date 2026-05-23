import os
from unittest.mock import MagicMock

import pytest

from bal_sbx.backends.user import UserSandbox
from bal_sbx.core.errors import SandboxBroken
from bal_sbx.core.identity import SandboxIdentity
from bal_sbx.core.paths import PathLayout
from bal_sbx.exec.launcher import SandboxedLauncher
from bal_sbx.registry.json_file import JsonFileRegistry


LAYOUT = PathLayout(home_root="/home", registry_path="/tmp/r.json")


def _identity(tmp_path) -> SandboxIdentity:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    return SandboxIdentity.from_workspace(str(workspace), LAYOUT)


def _ok_sandbox(fake_system_ops, identity):
    sandbox = UserSandbox(identity, fake_system_ops)
    sandbox.create()
    return sandbox


def _file_registry(tmp_path) -> JsonFileRegistry:
    return JsonFileRegistry(str(tmp_path / "registry.json"))


# ---- refuses on bad status ---------------------------------------------

def test_exec_replace_refuses_when_status_not_ok(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    sandbox = UserSandbox(identity, fake_system_ops)  # not created -> MISSING_USER
    launcher = SandboxedLauncher(sandbox, fake_system_ops, _file_registry(tmp_path))
    with pytest.raises(SandboxBroken):
        launcher.exec_replace(["echo", "hi"])


def test_run_refuses_when_status_not_ok(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    sandbox = UserSandbox(identity, fake_system_ops)
    launcher = SandboxedLauncher(sandbox, fake_system_ops, _file_registry(tmp_path))
    with pytest.raises(SandboxBroken):
        launcher.run(["echo", "hi"])


def test_does_not_touch_registry_when_broken(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    sandbox = UserSandbox(identity, fake_system_ops)
    registry = MagicMock(spec=JsonFileRegistry)
    launcher = SandboxedLauncher(sandbox, fake_system_ops, registry)
    with pytest.raises(SandboxBroken):
        launcher.exec_replace(["x"])
    registry.touch.assert_not_called()


# ---- argv construction --------------------------------------------------

def test_exec_replace_argv_shape(monkeypatch, fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    sandbox = _ok_sandbox(fake_system_ops, identity)
    launcher = SandboxedLauncher(sandbox, fake_system_ops, _file_registry(tmp_path))

    captured: dict = {}

    def fake_execvp(file, args):
        captured["file"] = file
        captured["args"] = list(args)

    monkeypatch.setattr(os, "execvp", fake_execvp)
    with pytest.raises(RuntimeError):
        launcher.exec_replace(["agent", "--flag", "v"])

    assert captured["file"] == "sudo"
    head = captured["args"][:6]
    assert head == ["sudo", "-u", identity.user, "-H", "env", "-i"]
    tail = captured["args"][-3:]
    assert tail == ["agent", "--flag", "v"]
    pairs = captured["args"][6:-3]
    assert all("=" in pair for pair in pairs)
    keys = {pair.split("=", 1)[0] for pair in pairs}
    assert {
        "HOME",
        "USER",
        "LOGNAME",
        "PATH",
        "BAL_SANDBOX_ID",
        "BAL_SANDBOX_WORKSPACE",
    } <= keys


def test_exec_replace_applies_env_overrides(monkeypatch, fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    sandbox = _ok_sandbox(fake_system_ops, identity)
    launcher = SandboxedLauncher(sandbox, fake_system_ops, _file_registry(tmp_path))

    captured: dict = {}
    monkeypatch.setattr(
        os, "execvp", lambda _f, args: captured.setdefault("args", list(args))
    )
    with pytest.raises(RuntimeError):
        launcher.exec_replace(["agent"], env_overrides={"FOO": "bar"})

    pairs = captured["args"][6:-1]
    assert "FOO=bar" in pairs


# ---- ordering: touch before exec ---------------------------------------

def test_exec_replace_calls_touch_before_execvp(monkeypatch, fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    sandbox = _ok_sandbox(fake_system_ops, identity)
    registry = MagicMock(spec=JsonFileRegistry)
    launcher = SandboxedLauncher(sandbox, fake_system_ops, registry)

    manager = MagicMock()
    manager.attach_mock(registry.touch, "touch")
    fake_execvp = MagicMock()
    manager.attach_mock(fake_execvp, "execvp")
    monkeypatch.setattr(os, "execvp", fake_execvp)

    with pytest.raises(RuntimeError):
        launcher.exec_replace(["agent"])

    names = [c[0] for c in manager.mock_calls]
    assert "touch" in names and "execvp" in names
    assert names.index("touch") < names.index("execvp")
    registry.touch.assert_called_once_with(identity.id)


# ---- run() --------------------------------------------------------------

def test_run_returns_subprocess_exit_code(monkeypatch, fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    sandbox = _ok_sandbox(fake_system_ops, identity)
    launcher = SandboxedLauncher(sandbox, fake_system_ops, _file_registry(tmp_path))

    monkeypatch.setattr(
        "bal_sbx.exec.launcher.subprocess.run",
        lambda *a, **kw: MagicMock(returncode=7),
    )
    assert launcher.run(["agent", "fail"]) == 7


def test_run_does_not_raise_on_nonzero(monkeypatch, fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    sandbox = _ok_sandbox(fake_system_ops, identity)
    launcher = SandboxedLauncher(sandbox, fake_system_ops, _file_registry(tmp_path))

    monkeypatch.setattr(
        "bal_sbx.exec.launcher.subprocess.run",
        lambda *a, **kw: MagicMock(returncode=2),
    )
    assert launcher.run(["agent"]) == 2


def test_run_touches_registry(monkeypatch, fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    sandbox = _ok_sandbox(fake_system_ops, identity)
    registry = MagicMock(spec=JsonFileRegistry)
    launcher = SandboxedLauncher(sandbox, fake_system_ops, registry)
    monkeypatch.setattr(
        "bal_sbx.exec.launcher.subprocess.run",
        lambda *a, **kw: MagicMock(returncode=0),
    )
    launcher.run(["agent"])
    registry.touch.assert_called_once_with(identity.id)


def test_run_argv_matches_exec_replace_shape(monkeypatch, fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    sandbox = _ok_sandbox(fake_system_ops, identity)
    launcher = SandboxedLauncher(sandbox, fake_system_ops, _file_registry(tmp_path))

    captured: dict = {}

    def fake_run(argv, check=False):
        captured["argv"] = list(argv)
        return MagicMock(returncode=0)

    monkeypatch.setattr("bal_sbx.exec.launcher.subprocess.run", fake_run)
    launcher.run(["agent", "x"])
    assert captured["argv"][:6] == ["sudo", "-u", identity.user, "-H", "env", "-i"]
    assert captured["argv"][-2:] == ["agent", "x"]
