import pytest

from bal_sbx.backends.factory import build_sandbox
from bal_sbx.backends.user import UserSandbox
from bal_sbx.core.identity import SandboxIdentity
from bal_sbx.core.paths import PathLayout


LAYOUT = PathLayout(home_root="/home", registry_path="/tmp/registry.json")


def _identity(tmp_path) -> SandboxIdentity:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    return SandboxIdentity.from_workspace(str(workspace), LAYOUT)


def test_build_user_sandbox(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    sandbox = build_sandbox("user", identity, fake_system_ops)
    assert isinstance(sandbox, UserSandbox)
    assert sandbox.identity is identity


def test_build_unknown_kind_raises(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    with pytest.raises(ValueError, match="docker"):
        build_sandbox("docker", identity, fake_system_ops)


def test_build_empty_kind_raises(fake_system_ops, tmp_path):
    identity = _identity(tmp_path)
    with pytest.raises(ValueError):
        build_sandbox("", identity, fake_system_ops)
