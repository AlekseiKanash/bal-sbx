import os
import subprocess
from unittest.mock import MagicMock

import pytest

from bal_sbx.system.home import RealHomeLayout
from bal_sbx.system.privilege import PrivilegeBroker


class LocalBroker(PrivilegeBroker):
    """Test broker: runs argv directly (no sudo).

    tmp_path is already user-writable, so we skip elevation and just exercise
    the same argv RealHomeLayout would send to sudo in production.
    """

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run_privileged(self, argv: list[str]) -> subprocess.CompletedProcess:
        self.calls.append(argv)
        return subprocess.run(argv, check=True, capture_output=True, text=True)

    def is_available(self) -> bool:
        return True


@pytest.fixture
def broker():
    return LocalBroker()


def test_create_makes_directory(broker, tmp_path):
    home = tmp_path / "alice"
    RealHomeLayout(broker).create(str(home), os.getenv("USER", "nobody"))
    assert home.is_dir()


def test_create_routes_mkdir_and_chown_through_broker(tmp_path):
    spy = MagicMock(spec=PrivilegeBroker)
    home = tmp_path / "alice"
    RealHomeLayout(spy).create(str(home), "alice")
    assert spy.run_privileged.call_args_list == [
        (([ "mkdir", "-p", str(home) ],),),
        (([ "chown", "alice", str(home) ],),),
    ]


def test_create_is_idempotent(broker, tmp_path):
    home = tmp_path / "alice"
    user = os.getenv("USER", "nobody")
    layout = RealHomeLayout(broker)
    layout.create(str(home), user)
    layout.create(str(home), user)
    assert home.is_dir()


def test_destroy_removes_existing_home(broker, tmp_path):
    home = tmp_path / "alice"
    home.mkdir()
    (home / "data.txt").write_text("payload")
    RealHomeLayout(broker).destroy(str(home))
    assert not home.exists()


def test_destroy_absent_home_is_noop(tmp_path):
    spy = MagicMock(spec=PrivilegeBroker)
    RealHomeLayout(spy).destroy(str(tmp_path / "ghost"))
    spy.run_privileged.assert_not_called()


def test_exists_true_for_directory(broker, tmp_path):
    home = tmp_path / "alice"
    home.mkdir()
    assert RealHomeLayout(broker).exists(str(home)) is True


def test_exists_false_for_missing(broker, tmp_path):
    assert RealHomeLayout(broker).exists(str(tmp_path / "ghost")) is False


def test_link_workspace_creates_symlink(broker, tmp_path):
    home = tmp_path / "alice"
    home.mkdir()
    workspace = tmp_path / "proj"
    workspace.mkdir()
    RealHomeLayout(broker).link_workspace(str(home), str(workspace))
    link = home / ".bal" / "workspace"
    assert link.is_symlink()
    assert os.readlink(link) == str(workspace)


def test_link_workspace_replaces_existing_link(broker, tmp_path):
    home = tmp_path / "alice"
    home.mkdir()
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    layout = RealHomeLayout(broker)
    layout.link_workspace(str(home), str(a))
    layout.link_workspace(str(home), str(b))
    assert os.readlink(home / ".bal" / "workspace") == str(b)


def test_workspace_link_target_returns_target(broker, tmp_path):
    home = tmp_path / "alice"
    home.mkdir()
    workspace = tmp_path / "proj"
    workspace.mkdir()
    layout = RealHomeLayout(broker)
    layout.link_workspace(str(home), str(workspace))
    assert layout.workspace_link_target(str(home)) == str(workspace)


def test_workspace_link_target_none_when_missing(broker, tmp_path):
    home = tmp_path / "alice"
    home.mkdir()
    assert RealHomeLayout(broker).workspace_link_target(str(home)) is None


def test_link_workspace_routes_through_privilege_broker(tmp_path):
    spy = MagicMock(spec=PrivilegeBroker)
    home = tmp_path / "alice"
    home.mkdir()
    workspace = tmp_path / "proj"
    workspace.mkdir()
    RealHomeLayout(spy).link_workspace(str(home), str(workspace))
    link = str(home / ".bal" / "workspace")
    parent = str(home / ".bal")
    assert spy.run_privileged.call_args_list == [
        (([ "mkdir", "-p", parent ],),),
        (([ "ln", "-sfn", str(workspace), link ],),),
    ]
